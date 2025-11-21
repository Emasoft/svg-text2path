// SPDX-License-Identifier: GPL-2.0-or-later
#include "style-attachments.h"
#include "display/drawing-text.h"
#include "object/sp-paint-server.h"
#include "object/sp-filter.h"

namespace Inkscape {
namespace Text {

void StyleAttachments::attachFilter(DrawingText *item, SPFilter *filter)
{
    _filters.try_emplace(filter, filter).first->second.addItem(item);
}

void StyleAttachments::attachFill(DrawingText *item, SPPaintServer *paintserver, Geom::OptRect const &bbox)
{
    _patterns.try_emplace(paintserver, paintserver).first->second.addFill(item, bbox);
}

void StyleAttachments::attachStroke(DrawingText *item, SPPaintServer *paintserver, Geom::OptRect const &bbox)
{
    _patterns.try_emplace(paintserver, paintserver).first->second.addStroke(item, bbox);
}

void StyleAttachments::unattachAll()
{
    _filters.clear();
    _patterns.clear();
}

StyleAttachments::FilterEntry::FilterEntry(SPFilter *filter)
{
    _filter = filter;
    _conn = _filter->connectRelease([this] (auto) { _removeAllItems(); });
}

StyleAttachments::FilterEntry::~FilterEntry()
{
    _removeAllItems();
    _conn.disconnect();
}

void StyleAttachments::FilterEntry::addItem(DrawingText *item)
{
    _filter->show(item);
    _items.emplace_back(item);
}

void StyleAttachments::FilterEntry::_removeAllItems()
{
    for (auto item : _items) {
        _filter->hide(item);
    }
    _items.clear();
}

StyleAttachments::PatternEntry::PatternEntry(SPPaintServer *paintserver)
{
    _paintserver = paintserver;
    _conn = _paintserver->connectRelease([this] (auto) { _removeAllItems(); });
}

StyleAttachments::PatternEntry::~PatternEntry()
{
    _removeAllItems();
    _conn.disconnect();
}

void StyleAttachments::PatternEntry::addFill(DrawingText *item, Geom::OptRect const &bbox)
{
    auto key = SPItem::display_key_new(1);
    auto pattern = _paintserver->show(item->drawing(), key, bbox);
    item->setFillPattern(pattern);
    _keys.emplace_back(key);
}

void StyleAttachments::PatternEntry::addStroke(DrawingText *item, Geom::OptRect const &bbox)
{
    auto key = SPItem::display_key_new(1);
    auto pattern = _paintserver->show(item->drawing(), key, bbox);
    item->setStrokePattern(pattern);
    _keys.emplace_back(key);
}

void StyleAttachments::PatternEntry::_removeAllItems()
{
    for (auto key : _keys) {
        _paintserver->hide(key);
    }
    _keys.clear();
}

} // namespace Text
} // namespace Inkscape

/*
  Local Variables:
  mode:c++
  c-file-style:"stroustrup"
  c-file-offsets:((innamespace . 0)(inline-open . 0)(case-label . +))
  indent-tabs-mode:nil
  fill-column:99
  End:
*/
// vim: filetype=cpp:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:fileencoding=utf-8 :
