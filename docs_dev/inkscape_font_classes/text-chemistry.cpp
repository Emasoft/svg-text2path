// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Text commands
 *
 * Authors:
 *   bulia byak
 *   Jon A. Cruz <jon@joncruz.org>
 *   Abhishek Sharma
 *
 * Copyright (C) 2004 authors
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */

#include <cstring>
#include <string>
#include <glibmm/i18n.h>
#include <glibmm/regex.h>


#include "desktop.h"
#include "document-undo.h"
#include "document.h"
#include "inkscape-application.h"
#include "inkscape.h"
#include "message-stack.h"
#include "preferences.h"
#include "selection.h"
#include "svg/svg.h"
#include "text-chemistry.h"
#include "text-editing.h"

#include "object/sp-flowdiv.h"
#include "object/sp-flowregion.h"
#include "object/sp-flowtext.h"
#include "object/sp-textpath.h"
#include "object/sp-tspan.h"
#include "style.h"
#include "ui/icon-names.h"

#include "xml/repr.h"

using Inkscape::DocumentUndo;

static SPItem *text_or_flowtext_in_selection(Inkscape::Selection *selection)
{
    for (auto item : selection->items()) {
        if (is<SPText>(item) || is<SPFlowtext>(item)) {
            return item;
        }
    }
    return nullptr;
}

static SPItem *
shape_in_selection(Inkscape::Selection *selection)
{
    for (auto item : selection->items()) {
        if (is<SPShape>(item)) {
            return item;
        }
    }
    return nullptr;
}

void
text_put_on_path()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;
    if (!desktop)
        return;

    Inkscape::Selection *selection = desktop->getSelection();

    SPItem *text = text_or_flowtext_in_selection(selection);
    SPItem *shape = shape_in_selection(selection);

    Inkscape::XML::Document *xml_doc = desktop->doc()->getReprDoc();

    if (!text || !shape || std::ranges::distance(selection->items()) != 2) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>a text and a path</b> to put text on path."));
        return;
    }

    if (SP_IS_TEXT_TEXTPATH(text)) {
        desktop->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("This text object is <b>already put on a path</b>. Remove it from the path first. Use <b>Shift+D</b> to look up its path."));
        return;
    }

    // if a flowed text is selected, convert it to a regular text object
    if (is<SPFlowtext>(text)) {

        if (!cast_unsafe<SPFlowtext>(text)->layout.outputExists()) {
            desktop->messageStack()->
                flash(Inkscape::WARNING_MESSAGE,
                      _("The flowed text(s) must be <b>visible</b> in order to be put on a path."));
        }

        Inkscape::XML::Node *repr = cast<SPFlowtext>(text)->getAsText();

        if (!repr) return;

        Inkscape::XML::Node *parent = text->getRepr()->parent();
        parent->appendChild(repr);

        SPItem *new_item = (SPItem *) desktop->getDocument()->getObjectByRepr(repr);
        new_item->doWriteTransform(text->transform);
        new_item->updateRepr();

        Inkscape::GC::release(repr);
        text->deleteObject(); // delete the original flowtext

        desktop->getDocument()->ensureUpToDate();

        selection->clear();

        text = new_item; // point to the new text
    }

    if (auto textitem = cast<SPText>(text)) {
        // Replace any new lines (including sodipodi:role="line") by spaces.
        textitem->remove_newlines();
    }

    Inkscape::Text::Layout const *layout = te_get_layout(text);
    Inkscape::Text::Layout::Alignment text_alignment = layout->paragraphAlignment(layout->begin());

    // remove transform from text, but recursively scale text's fontsize by the expansion
    cast<SPText>(text)->_adjustFontsizeRecursive (text, text->transform.descrim());
    text->removeAttribute("transform");

    // make a list of text children
    std::vector<Inkscape::XML::Node *> text_reprs;
    for(auto& o: text->children) {
        text_reprs.push_back(o.getRepr());
    }

    // create textPath and put it into the text
    Inkscape::XML::Node *textpath = xml_doc->createElement("svg:textPath");
    // reference the shape
    gchar *href_str = g_strdup_printf("#%s", shape->getRepr()->attribute("id"));
    textpath->setAttribute("xlink:href", href_str);
    g_free(href_str);
    if (text_alignment == Inkscape::Text::Layout::RIGHT) {
        textpath->setAttribute("startOffset", "100%");
    } else if (text_alignment == Inkscape::Text::Layout::CENTER) {
        textpath->setAttribute("startOffset", "50%");
    }
    text->getRepr()->addChild(textpath, nullptr);

    for (auto i=text_reprs.rbegin();i!=text_reprs.rend();++i) {
        // Make a copy of each text child
        Inkscape::XML::Node *copy = (*i)->duplicate(xml_doc);
        // We cannot have multiline in textpath, so remove line attrs from tspans
        if (!strcmp(copy->name(), "svg:tspan")) {
            copy->removeAttribute("sodipodi:role");
            copy->removeAttribute("x");
            copy->removeAttribute("y");
        }
        // remove the old repr from under text
        text->getRepr()->removeChild(*i);
        // put its copy into under textPath
        textpath->addChild(copy, nullptr); // fixme: copy id
    }

    // x/y are useless with textpath, and confuse Batik 1.5
    text->removeAttribute("x");
    text->removeAttribute("y");

    DocumentUndo::done(desktop->getDocument(), _("Put text on path"), INKSCAPE_ICON("draw-text"));
}

void
text_remove_from_path()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;

    Inkscape::Selection *selection = desktop->getSelection();

    if (selection->isEmpty()) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>a text on path</b> to remove it from path."));
        return;
    }

    bool did = false;
    auto items = selection->items();
    for(auto obj : items){
        if (SP_IS_TEXT_TEXTPATH(obj)) {
            SPObject *tp = obj->firstChild();

            did = true;

            sp_textpath_to_text(tp);
        }
    }

    if (!did) {
        desktop->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("<b>No texts-on-paths</b> in the selection."));
    } else {
        DocumentUndo::done(desktop->getDocument(), _("Remove text from path"), INKSCAPE_ICON("draw-text"));
    }
}

static void
text_remove_all_kerns_recursively(SPObject *o)
{
    o->removeAttribute("dx");
    o->removeAttribute("dy");
    o->removeAttribute("rotate");

    // if x contains a list, leave only the first value
    gchar const *x = o->getRepr()->attribute("x");
    if (x) {
        gchar **xa_space = g_strsplit(x, " ", 0);
        gchar **xa_comma = g_strsplit(x, ",", 0);
        if (xa_space && *xa_space && *(xa_space + 1)) {
            o->setAttribute("x", *xa_space);
        } else if (xa_comma && *xa_comma && *(xa_comma + 1)) {
            o->setAttribute("x", *xa_comma);
        }
        g_strfreev(xa_space);
        g_strfreev(xa_comma);
    }

    for (auto& i: o->children) {
        text_remove_all_kerns_recursively(&i);
        i.requestDisplayUpdate(SP_OBJECT_MODIFIED_FLAG | SP_TEXT_LAYOUT_MODIFIED_FLAG);
    }
}

//FIXME: must work with text selection
void
text_remove_all_kerns()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;

    Inkscape::Selection *selection = desktop->getSelection();

    if (selection->isEmpty()) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>text(s)</b> to remove kerns from."));
        return;
    }

    bool did = false;

    auto items = selection->items();
    for(auto obj : items){
        if (!is<SPText>(obj) && !is<SPTSpan>(obj) && !is<SPFlowtext>(obj)) {
            continue;
        }

        text_remove_all_kerns_recursively(obj);
        obj->requestDisplayUpdate(SP_OBJECT_MODIFIED_FLAG | SP_TEXT_LAYOUT_MODIFIED_FLAG);
        did = true;
    }

    if (!did) {
        desktop->messageStack()->flash(Inkscape::ERROR_MESSAGE, _("Select <b>text(s)</b> to remove kerns from."));
    } else {
        DocumentUndo::done(desktop->getDocument(), _("Remove manual kerns"), INKSCAPE_ICON("draw-text"));
    }
}

void
text_flow_shape_subtract()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;
    if (!desktop)
        return;

    SPDocument *doc = desktop->getDocument();
    Inkscape::Selection *selection = desktop->getSelection();
    SPItem *text = text_or_flowtext_in_selection(selection);

    if (is<SPText>(text)) {
        // Make list of all shapes.
        Glib::ustring shapes;
        auto items = selection->items();
        for (auto item : items) {
            if (is<SPShape>(item)) {
                if (!shapes.empty()) shapes += " ";
                shapes += item->getUrl();
            }
        }

        // Set 'shape-subtract' property.
        text->style->shape_subtract.read(shapes.c_str());
        text->updateRepr();

        DocumentUndo::done(doc, _("Flow text subtract shape"), INKSCAPE_ICON("draw-text"));
    } else {
        // SVG 1.2 Flowed Text
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Subtraction not available for SVG 1.2 Flowed text."));
    }
}

void
text_flow_into_shape()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;
    if (!desktop)
        return;

    SPDocument *doc = desktop->getDocument();
    Inkscape::XML::Document *xml_doc = doc->getReprDoc();

    Inkscape::Selection *selection = desktop->getSelection();

    SPItem *text = text_or_flowtext_in_selection(selection);
    SPItem *shape = shape_in_selection(selection);

    if (!text || !shape || std::ranges::distance(selection->items()) < 2) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>a text</b> and one or more <b>paths or shapes</b> to flow text."));
        return;
    }

    auto prefs = Inkscape::Preferences::get();
    if (prefs->getBool("/tools/text/use_svg2", true)) {
        // SVG 2 Text

        if (is<SPText>(text)) {
            // Make list of all shapes.
            Glib::ustring shapes;
            auto items = selection->items();
            for (auto item : items) {
                if (is<SPShape>(item)) {
                    if (!shapes.empty()) {
                        shapes += " ";
                    } else {
                        // can only take one shape into account for transform compensation
                        // compensate transform
                        auto const new_transform = i2i_affine(item->parent, text->parent);
                        auto const ex = text->transform.descrim() / new_transform.descrim();
                        static_cast<SPText *>(text)->_adjustFontsizeRecursive(text, ex);
                        text->transform = new_transform;
                    }

                    shapes += item->getUrl();
                }
            }

            // Set 'shape-inside' property.
            text->style->shape_inside.read(shapes.c_str());
            text->style->white_space.read("pre-wrap"); // Respect new lines.
            text->updateRepr();

            DocumentUndo::done(doc, _("Flow text into shape"), INKSCAPE_ICON("draw-text"));
        }
    } else {
        if (is<SPText>(text) || is<SPFlowtext>(text)) {
            // remove transform from text, but recursively scale text's fontsize by the expansion
            auto ex = i2i_affine(text, shape->parent).descrim();
            cast<SPText>(text)->_adjustFontsizeRecursive(text, ex);
            text->removeAttribute("transform");
        }

        Inkscape::XML::Node *root_repr = xml_doc->createElement("svg:flowRoot");
        root_repr->setAttribute("xml:space", "preserve"); // we preserve spaces in the text objects we create
        root_repr->setAttribute("style", text->getRepr()->attribute("style")); // fixme: transfer style attrs too
        shape->parent->getRepr()->appendChild(root_repr);
        SPObject *root_object = doc->getObjectByRepr(root_repr);
        g_return_if_fail(is<SPFlowtext>(root_object));

        Inkscape::XML::Node *region_repr = xml_doc->createElement("svg:flowRegion");
        root_repr->appendChild(region_repr);
        SPObject *object = doc->getObjectByRepr(region_repr);
        g_return_if_fail(is<SPFlowregion>(object));

        /* Add clones */
        auto items = selection->items();
        for(auto item : items){
            if (is<SPShape>(item)){
                Inkscape::XML::Node *clone = xml_doc->createElement("svg:use");
                clone->setAttribute("x", "0");
                clone->setAttribute("y", "0");
                gchar *href_str = g_strdup_printf("#%s", item->getRepr()->attribute("id"));
                clone->setAttribute("xlink:href", href_str);
                g_free(href_str);

                // add the new clone to the region
                region_repr->appendChild(clone);
            }
        }

        if (is<SPText>(text)) { // flow from text, as string
            Inkscape::XML::Node *para_repr = xml_doc->createElement("svg:flowPara");
            root_repr->appendChild(para_repr);
            object = doc->getObjectByRepr(para_repr);
            g_return_if_fail(is<SPFlowpara>(object));

            Inkscape::Text::Layout const *layout = te_get_layout(text);
            Glib::ustring text_ustring = sp_te_get_string_multiline(text, layout->begin(), layout->end());

            Inkscape::XML::Node *text_repr = xml_doc->createTextNode(text_ustring.c_str()); // FIXME: transfer all formatting! and convert newlines into flowParas!
            para_repr->appendChild(text_repr);

            Inkscape::GC::release(para_repr);
            Inkscape::GC::release(text_repr);

        } else { // reflow an already flowed text, preserving paras
            for(auto& o: text->children) {
                if (is<SPFlowpara>(&o)) {
                    Inkscape::XML::Node *para_repr = o.getRepr()->duplicate(xml_doc);
                    root_repr->appendChild(para_repr);
                    object = doc->getObjectByRepr(para_repr);
                    g_return_if_fail(is<SPFlowpara>(object));
                    Inkscape::GC::release(para_repr);
                }
            }
        }

        text->deleteObject(true);

        DocumentUndo::done(doc, _("Flow text into shape"), INKSCAPE_ICON("draw-text"));

        desktop->getSelection()->set(cast<SPItem>(root_object));

        Inkscape::GC::release(root_repr);
        Inkscape::GC::release(region_repr);
    }
}

void
text_unflow ()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;
    if (!desktop)
        return;

    SPDocument *doc = desktop->getDocument();
    Inkscape::XML::Document *xml_doc = doc->getReprDoc();

    Inkscape::Selection *selection = desktop->getSelection();

    if (!text_or_flowtext_in_selection(selection) || std::ranges::distance(selection->items()) < 1) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>a flowed text</b> to unflow it."));
        return;
    }

    std::vector<SPItem*> new_objs;
    std::vector<SPItem *> old_objs;

    auto items = selection->items();
    for (auto i : items) {

        auto flowtext = cast<SPFlowtext>(i);
        auto text = cast<SPText>(i);

        if (flowtext) {

            // we discard transform when unflowing, but we must preserve expansion which is visible as
            // font size multiplier
            double ex = (flowtext->transform).descrim();

            Glib::ustring text_string = sp_te_get_string_multiline(flowtext);
            if (text_string.empty()) { // flowtext is empty
                continue;
            }

            /* Create <text> */
            Inkscape::XML::Node *rtext = xml_doc->createElement("svg:text");
            rtext->setAttribute("xml:space", "preserve"); // we preserve spaces in the text objects we create

            /* Set style */
            rtext->setAttribute("style", flowtext->getRepr()->attribute("style")); // fixme: transfer style attrs too;
                                                                                   // and from descendants

            Geom::OptRect bbox = flowtext->geometricBounds(flowtext->i2doc_affine());
            if (bbox) {
                Geom::Point xy = bbox->min();
                rtext->setAttributeSvgDouble("x", xy[Geom::X]);
                rtext->setAttributeSvgDouble("y", xy[Geom::Y]);
            }

            /* Create <tspan> */
            Inkscape::XML::Node *rtspan = xml_doc->createElement("svg:tspan");
            rtspan->setAttribute("sodipodi:role", "line"); // otherwise, why bother creating the tspan?
            rtext->addChild(rtspan, nullptr);

            Inkscape::XML::Node *text_repr = xml_doc->createTextNode(text_string.c_str()); // FIXME: transfer all formatting!!!
            rtspan->appendChild(text_repr);

            flowtext->parent->getRepr()->appendChild(rtext);
            SPObject *text_object = doc->getObjectByRepr(rtext);

            // restore the font size multiplier from the flowtext's transform
            auto text = cast<SPText>(text_object);
            text->_adjustFontsizeRecursive(text, ex);

            new_objs.push_back((SPItem *)text_object);
            old_objs.push_back(flowtext);

            Inkscape::GC::release(rtext);
            Inkscape::GC::release(rtspan);
            Inkscape::GC::release(text_repr);

        } else if (text) {
            if (text->has_shape_inside()) {

                auto old_point = text->getBaselinePoint();
                Inkscape::XML::Node *rtext = text->getRepr();

                // Position unflowed text near shape.
                Geom::OptRect bbox = text->geometricBounds(text->i2doc_affine());
                if (bbox) {
                    Geom::Point xy = bbox->min();
                    rtext->setAttributeSvgDouble("x", xy[Geom::X]);
                    rtext->setAttributeSvgDouble("y", xy[Geom::Y]);
                }

                // Remove 'shape-inside' property.
                SPCSSAttr *css = sp_repr_css_attr(rtext, "style");
                sp_repr_css_unset_property(css, "shape-inside");
                sp_repr_css_unset_property(css, "shape-padding");
                sp_repr_css_change(rtext, css, "style");
                sp_repr_css_attr_unref(css);

                // We'll leave tspans alone other than stripping 'x' and 'y' (this will preserve
                // styling).
                // We'll also remove temporarily 'sodipodi:role' (which shouldn't be
                // necessary later).
                for (auto j : text->childList(false)) {
                    auto tspan = cast<SPTSpan>(j);
                    if (tspan) {
                        tspan->getRepr()->removeAttribute("x");
                        tspan->getRepr()->removeAttribute("y");
                        tspan->getRepr()->removeAttribute("sodipodi:role");
                    }
                }
                // Reposition the text so the baselines don't change.
                text->rebuildLayout();
                auto new_point = text->getBaselinePoint();
                if (old_point && new_point) {
                    auto move = Geom::Translate(*old_point - *new_point) * text->transform;
                    text->doWriteTransform(move, &move, false);
                }
            }
        }
    }

    // For flowtext objects.
    if (new_objs.size() != 0) {

        // Update selection
        selection->clear();
        reverse(new_objs.begin(), new_objs.end());
        selection->setList(new_objs);

        // Delete old objects
        for (auto i : old_objs) {
            i->deleteObject(true);
        }
    }

    DocumentUndo::done(doc, _("Unflow flowed text"), INKSCAPE_ICON("draw-text"));
}

void
text_to_glyphs()
{
    auto doc = SP_ACTIVE_DOCUMENT;
    auto selection = InkscapeApplication::instance()->get_active_selection();
    std::vector<SPText*> results;
    std::vector<SPText*> to_delete;

    auto xml_doc = doc->getReprDoc();

    for(auto item : selection->items()) {
        auto text = cast<SPText>(item);
        if (!text)
            continue;

        auto parent = text->parent->getRepr();
        auto sibling = text->getRepr();

        auto const &layout = text->layout;
        auto iter = layout.end();
        while (iter != layout.begin()) {
            auto end = iter;
            // Glyph index may not be zero leading to an infinite loop
            // if we don't test this here... (see issue #4767).
            if (!iter.prevCharacter()) {
                break;
            }

            if (layout.isWhitespace(iter))
                continue;

            auto it_next = iter;
            int last_glyph = iter.glyphIndex();
            while (it_next.prevCharacter()) {
                // multiple characters single glyph ligature
                bool multi_char_glyph = it_next.glyphIndex() == last_glyph;
                // In some cases diacritics are separate glyphs and separate characters, but they can not
                // be used independently without base character.
                // Depends on specific font.
                bool helper_char = !layout.isCursorPosition(iter);
                if (multi_char_glyph || helper_char) {
                    iter = it_next;
                } else {
                    break;
                }
                last_glyph = it_next.glyphIndex();
            }
            // multiple glyphs from single character, get first glyph
            while (iter.glyphIndex() > 0 && layout.glyphs()[iter.glyphIndex() - 1].in_character ==
                                                layout.glyphs()[iter.glyphIndex()].in_character) {
                iter.prevGlyph();
            }

            Glib::ustring str;
            for (auto char_iter = iter; char_iter < end;) {
                if (layout.isWhitespace(char_iter)) {
                    break;
                }
                str.push_back(layout.characterAt(char_iter));
                if (!char_iter.nextCharacter()) {
                    break; // should not happen
                }
            }
            if (!iter.hasGlyph()) {
                continue;
            }
            auto glyph = layout.glyphs()[iter.glyphIndex()];

            SPObject *tspan = nullptr;
            layout.getSourceOfCharacter(iter, &tspan);
            if (!tspan)
                break;

            // Create new text object to hold the single glyph
            Inkscape::XML::Node *new_node = xml_doc->createElement("svg:text");

            // Write the effective style and transform back into the new text node
            SPStyle *result_style = new SPStyle(doc);
            for (auto sp = tspan->parent; sp && sp != text; sp = sp->parent) {
                result_style->merge(sp->style);
            }
            result_style->merge(text->style);
            result_style->text_anchor.read("start");
            // reset layout properties which are already included in glyph transform
            result_style->writing_mode = SP_CSS_WRITING_MODE_LR_TB;
            result_style->direction = SP_CSS_DIRECTION_LTR;
            Glib::ustring glyph_style = result_style->writeIfDiff(text->parent->style);
            delete result_style;

            new_node->setAttributeOrRemoveIfEmpty("style", glyph_style);
            auto const &glyph_span = glyph.span(&layout);
            auto inverse_scale = 1.0 / glyph_span.font_size;
            // not ideal, assumes that in case of 1 character -> n glyphs, the first glyph is the base glyph
            // and has normal position
            Geom::Affine transform =
                Geom::Scale(inverse_scale, -inverse_scale) // prevent font size from being applied twice
                * glyph.transform(layout) * text->transform;
            new_node->setAttributeOrRemoveIfEmpty("transform", sp_svg_transform_write(transform));
            new_node->appendChild(xml_doc->createTextNode(str.c_str()));

            // Store the new object for the selection and prepare for the next glyph
            parent->addChild(new_node, sibling);
            auto new_text = cast<SPText>(doc->getObjectByRepr(new_node));
            results.push_back(new_text);
            Inkscape::GC::release(new_node);
        }
        to_delete.push_back(text);
    }

    selection->clear();
    for (auto item : to_delete) {
        item->deleteObject();
    }

    if (results.empty()) {
        auto desktop = SP_ACTIVE_DESKTOP;
        if (desktop) {
            desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE, _("Select <b>text(s)</b> to convert to glyphs."));
        }
    } else {
        DocumentUndo::done(doc, _("Convert text to glyphs"), INKSCAPE_ICON("text-convert-to-regular"));
        selection->setList(results);
    }
}

void
flowtext_to_text()
{
    SPDesktop *desktop = SP_ACTIVE_DESKTOP;

    Inkscape::Selection *selection = desktop->getSelection();

    if (selection->isEmpty()) {
        desktop->messageStack()->flash(Inkscape::WARNING_MESSAGE,
                                                 _("Select <b>flowed text(s)</b> to convert."));
        return;
    }

    bool did = false;
    bool ignored = false;

    std::vector<Inkscape::XML::Node*> reprs;
    for (auto item : selection->items_vector()) {
        auto flowtext = cast<SPFlowtext>(item);
        if (!flowtext) {
            continue;
        }

        if (!flowtext->layout.outputExists()) {
            ignored = true;
            continue;
        }

        Inkscape::XML::Node *repr = flowtext->getAsText();

        if (!repr) break;

        did = true;

        Inkscape::XML::Node *parent = item->getRepr()->parent();
        parent->addChild(repr, item->getRepr());

        SPItem *new_item = cast_unsafe<SPItem>(desktop->getDocument()->getObjectByRepr(repr));
        new_item->doWriteTransform(item->transform);
        new_item->updateRepr();

        Inkscape::GC::release(repr);
        item->deleteObject();

        reprs.push_back(repr);
    }

    if (did) {
        DocumentUndo::done(desktop->getDocument(), _("Convert flowed text to text"), INKSCAPE_ICON("text-convert-to-regular"));
        selection->setReprList(reprs);
    } else if (ignored) {
        // no message for (did && ignored) because it is immediately overwritten
        desktop->messageStack()->
            flash(Inkscape::ERROR_MESSAGE,
                  _("Flowed text(s) must be <b>visible</b> in order to be converted."));

    } else {
        desktop->messageStack()->
            flash(Inkscape::ERROR_MESSAGE,
                  _("<b>No flowed text(s)</b> to convert in the selection."));
    }

}


Glib::ustring text_relink_shapes_str(gchar const *prop, std::map<Glib::ustring, Glib::ustring> const &old_to_new) {
    std::vector<Glib::ustring> shapes_url = Glib::Regex::split_simple(" ", prop);
    Glib::ustring res;
    for (auto shape_url : shapes_url) {
        if (shape_url.compare(0, 5, "url(#") != 0 || shape_url.compare(shape_url.size() - 1, 1, ")") != 0) {
            std::cerr << "text_relink_shapes_str: Invalid shape value: " << shape_url.raw() << std::endl;
        } else {
            auto old_id = shape_url.substr(5, shape_url.size() - 6);
            auto find_it = old_to_new.find(old_id);
            if (find_it != old_to_new.end()) {
                res.append("url(#").append(find_it->second).append(") ");
            } else {
                std::cerr << "Failed to replace reference " << old_id.raw() << std::endl;
            }
        }
    }
    // remove trailing space
    if (!res.empty()) {
        assert(res.raw().back() == ' ');
        res.resize(res.size() - 1);
    }
    return res;
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
