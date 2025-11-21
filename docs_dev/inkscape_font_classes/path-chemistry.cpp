// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Here are handlers for modifying selections, specific to paths
 *
 * Authors:
 *   Lauris Kaplinski <lauris@kaplinski.com>
 *   bulia byak <buliabyak@users.sf.net>
 *   Jasper van de Gronde <th.v.d.gronde@hccnet.nl>
 *   Jon A. Cruz <jon@joncruz.org>
 *   Abhishek Sharma
 *
 * Copyright (C) 1999-2008 Authors
 * Copyright (C) 2001-2002 Ximian, Inc.
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */

#include <ranges>
#include <string>
#include <glibmm/i18n.h>

#include "desktop.h"
#include "document-undo.h"
#include "document.h"
#include "helper/geom-pathstroke.h"
#include "message-stack.h"
#include "path-chemistry.h"
#include "text-editing.h"

#include "display/curve.h"

#include "object/box3d.h"
#include "object/object-set.h"
#include "object/sp-flowtext.h"
#include "object/sp-path.h"
#include "object/sp-root.h"
#include "object/sp-text.h"
#include "style.h"

#include "ui/icon-names.h"

#include "svg/svg.h"

#include "xml/repr.h"

using Inkscape::DocumentUndo;
using Inkscape::ObjectSet;

static void sp_degroup_list_recursive(std::vector<SPItem*> &out, SPItem *item)
{
    if (auto group = cast<SPGroup>(item)) {
        for (auto &child : group->children) {
            if (auto childitem = cast<SPItem>(&child)) {
                sp_degroup_list_recursive(out, childitem);
            }
        }
    } else {
        out.emplace_back(item);
    }
}

/// Replace all groups in the list with their member objects, recursively.
static std::vector<SPItem*> sp_degroup_list(std::vector<SPItem*> const &items)
{
    std::vector<SPItem*> out;
    for (auto item : items) {
        sp_degroup_list_recursive(out, item);
    }
    return out;
}

void ObjectSet::combine(bool skip_undo, bool silent)
{
    auto doc = document();
    auto items_copy = items_vector();
    
    if (items_copy.empty()) {
        if (desktop() && !silent) {
            desktop()->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>object(s)</b> to combine."));
        }
        return;
    }

    if (desktop()) {
        if (!silent) {
            desktop()->messageStack()->flash(Inkscape::IMMEDIATE_MESSAGE, _("Combining paths..."));
        }
        // set "busy" cursor
        desktop()->setWaitingCursor();
    }

    items_copy = sp_degroup_list(items_copy); // descend into any groups in selection

    std::vector<SPItem*> to_paths;
    for (auto item : items_copy | std::views::reverse) {
        if (!is<SPPath>(item) && !is<SPGroup>(item)) {
            to_paths.emplace_back(item);
        }
    }
    std::vector<Inkscape::XML::Node*> converted;
    bool did = sp_item_list_to_curves(to_paths, items_copy, converted);
    for (auto node : converted) {
        items_copy.emplace_back(static_cast<SPItem*>(doc->getObjectByRepr(node)));
    }

    items_copy = sp_degroup_list(items_copy); // converting to path may have added more groups, descend again

    std::sort(items_copy.begin(), items_copy.end(), [] (auto a, auto b) {
        return sp_repr_compare_position(a->getRepr(), b->getRepr()) < 0;
    });
    assert(!items_copy.empty()); // cannot be empty because of check at top of function

    // remember the position, id, transform and style of the topmost path, they will be assigned to the combined one
    int position = 0;
    char const *transform = nullptr;
    char const *path_effect = nullptr;

    Geom::PathVector curve;
    SPItem *first = nullptr;
    Inkscape::XML::Node *parent = nullptr; 

    if (did) {
        clear();
    }

    for (auto item : items_copy | std::views::reverse) {
        auto path = cast<SPPath>(item);
        if (!path) {
            continue;
        }

        if (!did) {
            clear();
            did = true;
        }

        auto c = *path->curveForEdit();
        if (!first) {  // this is the topmost path
            first = item;
            parent = first->getRepr()->parent();
            position = first->getRepr()->position();
            transform = first->getRepr()->attribute("transform");
            // FIXME: merge styles of combined objects instead of using the first one's style
            path_effect = first->getRepr()->attribute("inkscape:path-effect");
            //c->transform(item->transform);
            curve = std::move(c);
        } else {
            c *= item->getRelativeTransform(first);
            pathvector_append(curve, std::move(c));

            // reduce position only if the same parent
            if (item->getRepr()->parent() == parent) {
                position--;
            }
            // delete the object for real, so that its clones can take appropriate action
            item->deleteObject();
        }
    }

    if (did) {
        Inkscape::XML::Document *xml_doc = doc->getReprDoc();
        Inkscape::XML::Node *repr = xml_doc->createElement("svg:path");

        Inkscape::copy_object_properties(repr, first->getRepr());

        // delete the topmost.
        first->deleteObject(false);

        // restore id, transform, path effect, and style
        if (transform) {
            repr->setAttribute("transform", transform);
        }

        repr->setAttribute("inkscape:path-effect", path_effect);

        // set path data corresponding to new curve
        auto dstring = sp_svg_write_path(curve);
        if (path_effect) {
            repr->setAttribute("inkscape:original-d", dstring);
        } else {
            repr->setAttribute("d", dstring);
        }

        // add the new group to the parent of the topmost
        // move to the position of the topmost, reduced by the number of deleted items
        parent->addChildAtPos(repr, position > 0 ? position : 0);

        if (!skip_undo) {
            DocumentUndo::done(doc, _("Combine"), INKSCAPE_ICON("path-combine"));
        }
        set(repr);

        Inkscape::GC::release(repr);

    } else if (desktop() && !silent) {
        desktop()->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("<b>No path(s)</b> to combine in the selection."));
    }

    if (desktop()) {
        desktop()->clearWaitingCursor();
    }
}

void
ObjectSet::breakApart(bool skip_undo, bool overlapping, bool silent)
{
    if (isEmpty()) {
        if(desktop() && !silent)
            desktop()->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>path(s)</b> to break apart."));
        return;
    }
    if(desktop()){
        if (!silent) {
            desktop()->messageStack()->flash(Inkscape::IMMEDIATE_MESSAGE, _("Breaking apart paths..."));
        }
        // set "busy" cursor
        desktop()->setWaitingCursor();
    }

    bool did = false;

    for (auto item : items_vector()) {

        auto path = cast<SPPath>(item);
        if (!path) {
            continue;
        }

        if (!path->curveForEdit()) {
            continue;
        }
        auto pathv = *path->curveForEdit();

        did = true;

        Inkscape::XML::Node *parent = item->getRepr()->parent();
        gint pos = item->getRepr()->position();
        char const *id = item->getRepr()->attribute("id");
        auto const fill_rule = item->style->fill_rule.computed;

        // XML Tree being used directly here while it shouldn't be...
        gchar *style = g_strdup(item->getRepr()->attribute("style"));
        // XML Tree being used directly here while it shouldn't be...
        gchar *path_effect = g_strdup(item->getRepr()->attribute("inkscape:path-effect"));
        Geom::Affine transform = path->transform;
        // it's going to resurrect as one of the pieces, so we delete without advertisement
        SPDocument *document = item->document;
        item->deleteObject(false);

        auto list = Inkscape::split_non_intersecting_paths(std::move(pathv),
                                                           overlapping ? fill_justDont : to_livarot(fill_rule));

        std::vector<Inkscape::XML::Node*> reprs;
        for (auto const &curve : list) {

            Inkscape::XML::Node *repr = parent->document()->createElement("svg:path");
            repr->setAttribute("style", style);

            repr->setAttribute("inkscape:path-effect", path_effect);

            auto str = sp_svg_write_path(curve);
            if (path_effect)
                repr->setAttribute("inkscape:original-d", str);
            else
                repr->setAttribute("d", str);
            repr->setAttributeOrRemoveIfEmpty("transform", sp_svg_transform_write(transform));
            
            // add the new repr to the parent
            // move to the saved position
            parent->addChildAtPos(repr, pos);
            SPLPEItem *lpeitem = nullptr;
            if (path_effect && (( lpeitem = cast<SPLPEItem>(document->getObjectByRepr(repr)) )) ) {
                lpeitem->forkPathEffectsIfNecessary(1);
            }
            // if it's the first one, restore id
            if (&curve == &list.front())
                repr->setAttribute("id", id);

            reprs.push_back(repr);

            Inkscape::GC::release(repr);
        }
        setReprList(reprs);

        g_free(style);
        g_free(path_effect);
    }

    if (desktop()) {
        desktop()->clearWaitingCursor();
    }

    if (did) {
        if ( !skip_undo ) {
            DocumentUndo::done(document(), _("Break apart"), INKSCAPE_ICON("path-break-apart"));
        }
    } else if (desktop() && !silent) {
        desktop()->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("<b>No path(s)</b> to break apart in the selection."));
    }
}

void ObjectSet::toCurves(bool skip_undo, bool clonesjustunlink)
{
    if (isEmpty()) {
        if (desktop())
            desktop()->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>object(s)</b> to convert to path."));
        return;
    }
    
    bool did = false;
    if (desktop()) {
        desktop()->messageStack()->flash(Inkscape::IMMEDIATE_MESSAGE, _("Converting objects to paths..."));
        // set "busy" cursor
        desktop()->setWaitingCursor();
    }
    if (!clonesjustunlink) {
        unlinkRecursive(true, false, true);
    }
    auto selected = items_vector();
    std::vector<Inkscape::XML::Node*> to_select;
    auto items = selected;

    did = sp_item_list_to_curves(items, selected, to_select);
    if (did) {
        setReprList(to_select);
        addList(selected);
    }
    if (clonesjustunlink) {
        unlinkRecursive(true, false, true);
    }

    if (desktop()) {
        desktop()->clearWaitingCursor();
    }
    if (did && !skip_undo) {
        DocumentUndo::done(document(), _("Object to path"), INKSCAPE_ICON("object-to-path"));
    } else {
        if(desktop())
            desktop()->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("<b>No objects</b> to convert to path in the selection."));
        return;
    }
}

/** Converts the selected items to LPEItems if they are not already so; e.g. SPRects) */
void ObjectSet::toLPEItems()
{

    if (isEmpty()) {
        return;
    }
    unlinkRecursive(true);
    auto selected = items_vector();
    std::vector<Inkscape::XML::Node*> to_select;
    clear();
    auto items = selected;

    sp_item_list_to_curves(items, selected, to_select, true);

    setReprList(to_select);
    addList(selected);
}

static void collect_object_items(SPObject *object, std::vector<SPItem*> &items)
{
    for (auto &child : object->children) {
        if (auto child_item = cast<SPItem>(&child)) {
            items.push_back(child_item);
        } else {
            collect_object_items(&child, items);
        }
    }
}

bool
sp_item_list_to_curves(const std::vector<SPItem*> &items, std::vector<SPItem*>& selected, std::vector<Inkscape::XML::Node*> &to_select, bool skip_all_lpeitems)
{
    bool did = false;
    for (auto item : items){
        g_assert(item != nullptr);
        SPDocument *document = item->document;

        auto group = cast<SPGroup>(item);
        if ( skip_all_lpeitems &&
             cast<SPLPEItem>(item) && 
             !group ) // also convert objects in an SPGroup when skip_all_lpeitems is set.
        { 
            continue;
        }

        if (auto box = cast<SPBox3D>(item)) {
            // convert 3D box to ordinary group of paths; replace the old element in 'selected' with the new group
            Inkscape::XML::Node *repr = box->convert_to_group()->getRepr();
            
            if (repr) {
                to_select.insert(to_select.begin(),repr);
                did = true;
                selected.erase(remove(selected.begin(), selected.end(), item), selected.end());
            }

            continue;
        }
        // remember id
        char const *id = item->getRepr()->attribute("id");
        
        auto lpeitem = cast<SPLPEItem>(item);
        if (lpeitem && lpeitem->hasPathEffect()) {
            lpeitem->removeAllPathEffects(true);
            SPObject *elemref = document->getObjectById(id);
            if (elemref != item) {
                selected.erase(remove(selected.begin(), selected.end(), item), selected.end());
                did = true;
                if (elemref) {
                    //If the LPE item is a shape is converted to a path so we need to reupdate the item
                    item = cast<SPItem>(elemref);
                    selected.push_back(item);
                } else {
                    // item deleted. Possibly because original-d value has no segments
                    continue;
                }
            } else if (!lpeitem->hasPathEffect()) {
                did = true;
            }
        }

        if (is<SPPath>(item)) {
            // remove connector attributes
            if (item->getAttribute("inkscape:connector-type") != nullptr) {
                item->removeAttribute("inkscape:connection-start");
                item->removeAttribute("inkscape:connection-start-point");
                item->removeAttribute("inkscape:connection-end");
                item->removeAttribute("inkscape:connection-end-point");
                item->removeAttribute("inkscape:connector-type");
                item->removeAttribute("inkscape:connector-curvature");
                did = true;
            }
            continue; // already a path, and no path effect
        }

        if (group) {
            std::vector<SPItem*> item_list;
            // This convoluted system allows SPItem's in defs to be collected too
            collect_object_items(group, item_list);
            std::vector<Inkscape::XML::Node*> item_to_select;
            std::vector<SPItem*> item_selected;
            
            if (sp_item_list_to_curves(item_list, item_selected, item_to_select))
                did = true;


            continue;
        }

        Inkscape::XML::Node *repr = sp_selected_item_to_curved_repr(item, 0);
        if (!repr)
            continue;

        did = true;
        selected.erase(remove(selected.begin(), selected.end(), item), selected.end());

        // remember the position of the item
        gint pos = item->getRepr()->position();
        // remember parent
        Inkscape::XML::Node *parent = item->getRepr()->parent();
        // remember class
        char const *class_attr = item->getRepr()->attribute("class");

        // It's going to resurrect, so we delete without notifying listeners.
        item->deleteObject(false);

        // restore id
        repr->setAttribute("id", id);
        // restore class
        repr->setAttribute("class", class_attr);
        // add the new repr to the parent
        parent->addChildAtPos(repr, pos);

        /* Buglet: We don't re-add the (new version of the) object to the selection of any other
         * desktops where it was previously selected. */
        to_select.insert(to_select.begin(),repr);
        Inkscape::GC::release(repr);
    }
    
    return did;
}

void list_text_items_recursive(SPItem *root, std::vector<SPItem *> &items)
{
    for (auto &child : root->children) {
        auto item = cast<SPItem>(&child);
        if (is<SPText>(item) || is<SPFlowtext>(item)) {
            items.push_back(item);
        }
        if (is<SPGroup>(item)) {
            list_text_items_recursive(item, items);
        }
    }
}

/**
 * Convert all text in the document to path, in-place.
 */
void Inkscape::convert_text_to_curves(SPDocument *doc)
{
    std::vector<SPItem *> items;
    doc->ensureUpToDate();

    list_text_items_recursive(doc->getRoot(), items);
    for (auto item : items) {
        te_update_layout_now_recursive(item);
    }

    std::vector<SPItem *> selected;               // Not used
    std::vector<Inkscape::XML::Node *> to_select; // Not used

    sp_item_list_to_curves(items, selected, to_select);
}

Inkscape::XML::Node *sp_text_to_curve_repr(SPItem *item)
{
    Inkscape::XML::Document *xml_doc = item->getRepr()->document();
    auto target_doc = item->document;

    // Special treatment for text: convert each glyph to separate path, then group the paths
    auto layout = te_get_layout(item);

    // Save original text for accessibility.
    Glib::ustring original_text = sp_te_get_string_multiline(item, layout->begin(), layout->end());

    SPObject *prev_parent = nullptr;
    std::vector<std::pair<Geom::PathVector, SPStyle *>> curves;

    Inkscape::XML::Node *result = xml_doc->createElement("svg:g");
    // temporary add the group to doc, some of the transformation logic expects object to be within document tree
    item->parent->addChild(result);
    SPItem *tmpParent = cast<SPItem>(target_doc->getObjectByRepr(result));
    tmpParent->set_i2d_affine(item->i2dt_affine());

    bool need_group = false;
    Inkscape::Text::Layout::iterator iter = layout->begin();
    while (iter != layout->end()) {
        Inkscape::Text::Layout::iterator iter_next = iter;
        iter_next.nextGlyph(); // iter_next is one glyph ahead from iter
        if (iter == iter_next)
            break;

        /* This glyph's style */
        SPObject *pos_obj = nullptr;
        layout->getSourceOfCharacter(iter, &pos_obj);
        if (!pos_obj) // no source for glyph, abort
            break;
        while (is<SPString>(pos_obj) && pos_obj->parent) {
            pos_obj = pos_obj->parent; // SPStrings don't have style
        }

        // get path from iter to iter_next:
        std::vector<std::pair<std::string, Geom::Affine>> svgSnippets;
        auto curve = layout->convertToSVG(iter, iter_next, svgSnippets);
        iter = iter_next; // shift to next glyph

        if (curve.empty() && svgSnippets.empty()) { // whitespace glyph?
            continue;
        }

        for (auto &svgSnippet : svgSnippets) {
            auto doc = SPDocument::createNewDocFromMem(svgSnippet.first);
            if (!doc) {
                continue;
            }
            auto transform = svgSnippet.second * item->i2doc_affine();
            target_doc->import(*doc, result, nullptr, transform, nullptr, SPDocument::ImportRoot::UngroupSingle,
                               SPDocument::ImportLayersMode::ToGroup);
            need_group = true;
        }

        if (curve.empty()) {
            continue;
        }

        // Create a new path for each span to group glyphs into
        // which preserves styles such as paint-order
        if (!prev_parent || prev_parent != pos_obj) {
            // Record the style for the dying tspan tree (see sp_style_merge_from_dying_parent in style.cpp)
            auto style = pos_obj->style;
            for (auto sp = pos_obj->parent; sp && sp != item; sp = sp->parent) {
                style->merge(sp->style);
            }
            curves.emplace_back(curve, style);
        } else {
            for (auto &path : curve) {
                curves.back().first.push_back(path);
            }
        }

        prev_parent = pos_obj;
    }
    result->parent()->removeChild(result);

    if (curves.empty() && !need_group) {
        Inkscape::GC::release(result);
        return nullptr;
    }

    auto result_style = std::make_unique<SPStyle>(item->document);

    for (auto &[pathv, style] : curves) {
        Glib::ustring glyph_style = style->writeIfDiff(item->style);
        auto new_path = xml_doc->createElement("svg:path");
        new_path->setAttributeOrRemoveIfEmpty("style", glyph_style);
        new_path->setAttribute("d", sp_svg_write_path(pathv));
        if (curves.size() == 1 && !need_group) {
            Inkscape::GC::release(result);
            result = new_path;
            result_style->merge(style);
        } else {
            result->appendChild(new_path);
            Inkscape::GC::release(new_path);
        }
    }

    result_style->merge(item->style);
    Glib::ustring css = result_style->writeIfDiff(item->parent ? item->parent->style : nullptr);

    Inkscape::copy_object_properties(result, item->getRepr());
    result->setAttributeOrRemoveIfEmpty("style", css);
    result->setAttributeOrRemoveIfEmpty("transform", item->getRepr()->attribute("transform"));

    if (!original_text.empty()) {
        result->setAttribute("aria-label", original_text);
    }
    return result;
}

Inkscape::XML::Node *sp_selected_item_to_curved_repr(SPItem *item, guint32 /*text_grouping_policy*/)
{
    if (!item)
        return nullptr;

    Inkscape::XML::Document *xml_doc = item->getRepr()->document();

    if (is<SPText>(item) || is<SPFlowtext>(item)) {
        return sp_text_to_curve_repr(item);
    }

    Geom::PathVector curve;

    if (auto shape = cast<SPShape>(item); shape && shape->curveForEdit()) {
        curve = *shape->curveForEdit();
    } else {
        return nullptr;
    }

    // Prevent empty paths from being added to the document
    // otherwise we end up with zomby markup in the SVG file
    if (curve.empty()) {
        return nullptr;
    }

    Inkscape::XML::Node *repr = xml_doc->createElement("svg:path");

    Inkscape::copy_object_properties(repr, item->getRepr());

    /* Transformation */
    repr->setAttribute("transform", item->getRepr()->attribute("transform"));

    /* Style */
    Glib::ustring style_str =
        item->style->writeIfDiff(item->parent ? item->parent->style : nullptr); // TODO investigate possibility
    repr->setAttributeOrRemoveIfEmpty("style", style_str);

    /* Definition */
    repr->setAttribute("d", sp_svg_write_path(curve));
    return repr;
}

void
ObjectSet::pathReverse()
{
    if (isEmpty()) {
        if(desktop())
            desktop()->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>path(s)</b> to reverse."));
        return;
    }


    // set "busy" cursor
    if(desktop()){
        desktop()->setWaitingCursor();
        desktop()->messageStack()->flash(Inkscape::IMMEDIATE_MESSAGE, _("Reversing paths..."));
    }
    
    bool did = false;

    for (auto item : items_vector()) {
        auto path = cast<SPPath>(item);
        if (!path) {
            continue;
        }

        did = true;

        auto str = sp_svg_write_path(path->curveForEdit()->reversed());
        if ( path->hasPathEffectRecursive() ) {
            path->setAttribute("inkscape:original-d", str);
        } else {
            path->setAttribute("d", str);
        }

        // reverse nodetypes order (Bug #179866)
        gchar *nodetypes = g_strdup(path->getRepr()->attribute("sodipodi:nodetypes"));
        if ( nodetypes ) {
            path->setAttribute("sodipodi:nodetypes", g_strreverse(nodetypes));
            g_free(nodetypes);
        }

        path->update_patheffect(false);
    }
    if(desktop())
        desktop()->clearWaitingCursor();

    if (did) {
        DocumentUndo::done(document(), _("Reverse path"), INKSCAPE_ICON("path-reverse"));
    } else {
        if(desktop())
            desktop()->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("<b>No paths</b> to reverse in the selection."));
    }
}


/**
 * Copy generic attributes, like those from the "Object Properties" dialog,
 * but also style and transformation center.
 *
 * @param dest XML node to copy attributes to
 * @param src XML node to copy attributes from
 */
static void ink_copy_generic_attributes( //
    Inkscape::XML::Node *dest,           //
    Inkscape::XML::Node const *src)
{
    static char const *const keys[] = {
        // core
        "id",

        // clip & mask
        "clip-path",
        "mask",

        // style
        "style",
        "class",

        // inkscape
        "inkscape:highlight-color",
        "inkscape:label",
        "inkscape:transform-center-x",
        "inkscape:transform-center-y",

        // interactivity
        "onclick",
        "onmouseover",
        "onmouseout",
        "onmousedown",
        "onmouseup",
        "onmousemove",
        "onfocusin",
        "onfocusout",
        "onload",
    };

    for (auto *key : keys) {
        auto *value = src->attribute(key);
        if (value) {
            dest->setAttribute(key, value);
        }
    }
}


/**
 * Copy generic child elements, like those from the "Object Properties" dialog
 * (title and description) but also XML comments.
 *
 * Does not check if children of the same type already exist in dest.
 *
 * @param dest XML node to copy children to
 * @param src XML node to copy children from
 */
static void ink_copy_generic_children( //
    Inkscape::XML::Node *dest,         //
    Inkscape::XML::Node const *src)
{
    static std::set<std::string> const names{
        // descriptive elements
        "svg:title",
        "svg:desc",
    };

    for (const auto *child = src->firstChild(); child != nullptr; child = child->next()) {
        // check if this child should be copied
        if (!(child->type() == Inkscape::XML::NodeType::COMMENT_NODE || //
              (child->name() && names.count(child->name())))) {
            continue;
        }

        auto dchild = child->duplicate(dest->document());
        dest->appendChild(dchild);
        dchild->release();
    }
}


/**
 * Copy generic object properties, like:
 * - id
 * - label
 * - title
 * - description
 * - style
 * - clip
 * - mask
 * - transformation center
 * - highlight color
 * - interactivity (event attributes)
 *
 * @param dest XML node to copy to
 * @param src XML node to copy from
 */
void Inkscape::copy_object_properties( //
    Inkscape::XML::Node *dest,         //
    Inkscape::XML::Node const *src)
{
    ink_copy_generic_attributes(dest, src);
    ink_copy_generic_children(dest, src);
}


/*
  Local Variables:
  mode:c++
  c-file-style:"stroustrup"
  c-file-offsets:((innamespace . 0)(inline-open . 0)(case-label . +))
  indent-tabs-mode:nil
  fill-column:99
  End:
*/
// vim: filetype=cpp:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:fileencoding=utf-8:textwidth=99 :
