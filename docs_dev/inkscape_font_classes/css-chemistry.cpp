// SPDX-License-Identifier: GPL-2.0-or-later
//
// Created by Michael Kowalski on 6/2/25.

#include "css-chemistry.h"

class SPObject;

namespace Inkscape::Css {

bool transfer_item_style(SPObject* src, SPObject* dest) {
    if (!src || !dest) return false;

    auto style = src->getAttribute("style");
    if (style && *style) {
        dest->setAttribute("style", style);
        src->removeAttribute("style");
        return true;
    }
    return false;
}

bool remove_item_style(SPObject* obj) {
    if (!obj) return false;

    auto style = obj->getAttribute("style");
    if (style && *style) {
        obj->removeAttribute("style");
        return true;
    }
    return false;
}

} // Inkscape
