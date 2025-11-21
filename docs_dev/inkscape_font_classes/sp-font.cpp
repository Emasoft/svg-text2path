// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * SVG <font> element implementation
 *
 * Author:
 *   Felipe C. da S. Sanches <juca@members.fsf.org>
 *   Abhishek Sharma
 *
 * Copyright (C) 2008, Felipe C. da S. Sanches
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */

#include "sp-font.h"

#include "attributes.h"                              // for SPAttr
#include "document.h"                                // for SPDocument
#include "sp-glyph.h"                                // for SPGlyph

#include "object/sp-object.h"                        // for SPObject, SP_OBJ...
#include "xml/document.h"                            // for Document
#include "xml/node.h"                                // for Node


//I think we should have extra stuff here and in the set method in order to set default value as specified at http://www.w3.org/TR/SVG/fonts.html

// TODO determine better values and/or make these dynamic:
double FNT_DEFAULT_ADV = 1024;   // TODO determine proper default
double FNT_DEFAULT_ASCENT = 768; // TODO determine proper default
double FNT_UNITS_PER_EM = 1024;  // TODO determine proper default

SPFont::SPFont() : SPObject() {
    this->horiz_origin_x = 0;
    this->horiz_origin_y = 0;
    this->horiz_adv_x = FNT_DEFAULT_ADV;
    this->vert_origin_x = FNT_DEFAULT_ADV / 2.0;
    this->vert_origin_y = FNT_DEFAULT_ASCENT;
    this->vert_adv_y = FNT_UNITS_PER_EM;
}

SPFont::~SPFont() = default;

void SPFont::build(SPDocument *document, Inkscape::XML::Node *repr) {
	SPObject::build(document, repr);

	this->readAttr(SPAttr::HORIZ_ORIGIN_X);
	this->readAttr(SPAttr::HORIZ_ORIGIN_Y);
	this->readAttr(SPAttr::HORIZ_ADV_X);
	this->readAttr(SPAttr::VERT_ORIGIN_X);
	this->readAttr(SPAttr::VERT_ORIGIN_Y);
	this->readAttr(SPAttr::VERT_ADV_Y);

	document->addResource("font", this);
}

/**
 * Callback for child_added event.
 */
void SPFont::child_added(Inkscape::XML::Node *child, Inkscape::XML::Node *ref) {
    SPObject::child_added(child, ref);

    if (!_block) this->parent->requestModified(SP_OBJECT_MODIFIED_FLAG);
}


/**
 * Callback for remove_child event.
 */
void SPFont::remove_child(Inkscape::XML::Node* child) {
    SPObject::remove_child(child);

    if (!_block) this->parent->requestModified(SP_OBJECT_MODIFIED_FLAG);
}

void SPFont::release() {
    this->document->removeResource("font", this);

    SPObject::release();
}

void SPFont::set(SPAttr key, const gchar *value) {
    // TODO these are floating point, so some epsilon comparison would be good
    switch (key) {
        case SPAttr::HORIZ_ORIGIN_X:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : 0;

            if (number != this->horiz_origin_x){
                this->horiz_origin_x = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        case SPAttr::HORIZ_ORIGIN_Y:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : 0;

            if (number != this->horiz_origin_y){
                this->horiz_origin_y = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        case SPAttr::HORIZ_ADV_X:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : FNT_DEFAULT_ADV;

            if (number != this->horiz_adv_x){
                this->horiz_adv_x = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        case SPAttr::VERT_ORIGIN_X:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : FNT_DEFAULT_ADV / 2.0;

            if (number != this->vert_origin_x){
                this->vert_origin_x = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        case SPAttr::VERT_ORIGIN_Y:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : FNT_DEFAULT_ASCENT;

            if (number != this->vert_origin_y){
                this->vert_origin_y = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        case SPAttr::VERT_ADV_Y:
        {
            double number = value ? g_ascii_strtod(value, nullptr) : FNT_UNITS_PER_EM;

            if (number != this->vert_adv_y){
                this->vert_adv_y = number;
                this->requestModified(SP_OBJECT_MODIFIED_FLAG);
            }
            break;
        }
        default:
        	SPObject::set(key, value);
            break;
    }
}

/**
 * Receives update notifications.
 */
void SPFont::update(SPCtx *ctx, guint flags) {
    if (flags & (SP_OBJECT_MODIFIED_FLAG)) {
        this->readAttr(SPAttr::HORIZ_ORIGIN_X);
        this->readAttr(SPAttr::HORIZ_ORIGIN_Y);
        this->readAttr(SPAttr::HORIZ_ADV_X);
        this->readAttr(SPAttr::VERT_ORIGIN_X);
        this->readAttr(SPAttr::VERT_ORIGIN_Y);
        this->readAttr(SPAttr::VERT_ADV_Y);
    }

    SPObject::update(ctx, flags);
}

#define COPY_ATTR(rd,rs,key) (rd)->setAttribute((key), rs->attribute(key));

Inkscape::XML::Node* SPFont::write(Inkscape::XML::Document *xml_doc, Inkscape::XML::Node *repr, guint flags) {
    if ((flags & SP_OBJECT_WRITE_BUILD) && !repr) {
        repr = xml_doc->createElement("svg:font");
    }

    repr->setAttributeSvgDouble("horiz-origin-x", this->horiz_origin_x);
    repr->setAttributeSvgDouble("horiz-origin-y", this->horiz_origin_y);
    repr->setAttributeSvgDouble("horiz-adv-x", this->horiz_adv_x);
    repr->setAttributeSvgDouble("vert-origin-x", this->vert_origin_x);
    repr->setAttributeSvgDouble("vert-origin-y", this->vert_origin_y);
    repr->setAttributeSvgDouble("vert-adv-y", this->vert_adv_y);

    if (repr != this->getRepr()) {
        // All the below COPY_ATTR functions are directly using 
        //  the XML Tree while they shouldn't
        COPY_ATTR(repr, this->getRepr(), "horiz-origin-x");
        COPY_ATTR(repr, this->getRepr(), "horiz-origin-y");
        COPY_ATTR(repr, this->getRepr(), "horiz-adv-x");
        COPY_ATTR(repr, this->getRepr(), "vert-origin-x");
        COPY_ATTR(repr, this->getRepr(), "vert-origin-y");
        COPY_ATTR(repr, this->getRepr(), "vert-adv-y");
    }

    SPObject::write(xml_doc, repr, flags);

    return repr;
}

using Inkscape::XML::Node;

SPGlyph* SPFont::create_new_glyph(const char* name, const char* unicode) {

    Inkscape::XML::Document* xml_doc = document->getReprDoc();

    // create a new glyph
    Inkscape::XML::Node* grepr = xml_doc->createElement("svg:glyph");

    grepr->setAttribute("glyph-name", name);
    grepr->setAttribute("unicode", unicode);

    // Append the new glyph node to the current font
    getRepr()->appendChild(grepr);
    Inkscape::GC::release(grepr);

    // get corresponding object
    auto g = cast<SPGlyph>(document->getObjectByRepr(grepr));

    g_assert(g != nullptr);

    g->setCollectionPolicy(SPObject::COLLECT_WITH_PARENT);

    return g;
}

void SPFont::sort_glyphs() {
    auto* repr = getRepr();
    g_assert(repr);

    std::vector<std::pair<SPGlyph*, Node*>> glyphs;
    glyphs.reserve(repr->childCount());

    // collect all glyphs (SPGlyph and their representations) 
    for (auto&& node : children) {
        if (auto g = cast<SPGlyph>(&node)) {
            glyphs.emplace_back(g, g->getRepr());
            // keep representation around as it gets removed
            g->getRepr()->anchor();
        }
    }

    // now sort by unicode point
    std::stable_sort(begin(glyphs), end(glyphs), [](const std::pair<SPGlyph*, Node*>& a, const std::pair<SPGlyph*, Node*>& b) {
        // compare individual unicode points in each string one by one to establish glyph order
        // note: ustring operator< doesn't work as expected
        const auto& str1 = a.first->unicode;
        const auto& str2 = b.first->unicode;
        return std::lexicographical_compare(str1.begin(), str1.end(), str2.begin(), str2.end());
    });

    // remove all glyph nodes from the document; block notifications
    _block = true;

    for (auto&& glyph : glyphs) {
        repr->removeChild(glyph.second);
    }

    // re-add them in the desired order
    for (auto&& glyph : glyphs) {
        repr->appendChild(glyph.second);
        glyph.second->release();
    }

    _block = false;
    // notify listeners about the change
    parent->requestModified(SP_OBJECT_MODIFIED_FLAG);
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
// vim: filetype=cpp:expandtab:shiftwidth=4:tabstop=8:softtabstop=4 :
