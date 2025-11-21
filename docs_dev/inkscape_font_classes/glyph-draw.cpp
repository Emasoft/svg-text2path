// SPDX-License-Identifier: GPL-2.0-or-later
//
// Created by Michael Kowalski on 8/12/25.
//

#include "glyph-draw.h"

#include "display/cairo-utils.h"
#include "libnrtype/font-instance.h"

namespace Inkscape::Util {

void draw_glyph(const draw_glyph_params& params) {
    if (params.rect.hasZeroArea()) return;

    auto font = params.font;
    auto& rect = params.rect;
    auto& ctx = params.ctx;

    auto glyph = font->LoadGlyph(params.glyph_index);
    if (!glyph) {
        // bitmap font? svg font?
        //todo
        return;
    }

    double font_size = params.font_size;
    if (font_size == 0) {
        // try to find optimal size, so we don't clip any glyph
        auto max_size = glyph->bbox_exact.dimensions();
        if (params.draw_metrics) {
            // account for space for vertical lines showing character width
            max_size.x() = std::max(glyph->h_advance, max_size.x());
        }
        max_size.y() = std::max(font->GetMaxAscent() + font->GetMaxDescent(), max_size.y());
        // inflate the size by 10% to leave margins
        max_size *= 1.1;

        // limit the size to at most 70% of available area to leave space around
        // and stop glyphs from dominating the drawing;
        // the aim is to try and keep the same scale from glyph to glyph as far as possible
        auto size_limit = 0.70;
        Geom::Point size{1, 1};
        if (max_size.y() > 0) {
            size.y() = std::min(1.0 / max_size.y(), size_limit);
        }
        if (max_size.x() > 0) {
            size.x() = std::min(1.0 / max_size.x(), size_limit);
        }
        font_size = std::min(size.x() * rect.width(), size.y() * rect.height());
    }
    // shift all glyphs vertically by the same amount so the baseline doesn't fluctuate
    // when switching from one glyph to another
    auto shift = (rect.height() - font_size * (font->GetMaxAscent() - font->GetMaxDescent())) / 2;

    // check if the glyph fits; some fonts will need this correction, but it should be infrequent
    auto top = shift + glyph->bbox_exact.bottom() * font_size;
    auto bottom = shift + glyph->bbox_exact.top() * font_size;
    if (top >= rect.height()) {
        shift -= top - rect.height();
    }
    else if (bottom < 0) {
        shift += -bottom;
    }

    ctx->save();
    ctx->rectangle(rect.left(), rect.top(), rect.width(), rect.height());
    ctx->clip();

    if (params.draw_background) {
        auto& bg = params.background_color;
        ctx->set_source_rgba(bg.get_red(), bg.get_green(), bg.get_blue(), bg.get_alpha());
        ctx->paint();
    }

    ctx->translate(rect.left(), rect.bottom() - shift);
    ctx->scale(font_size, -font_size);
    auto w = static_cast<double>(rect.width()) / font_size;
    auto midpoint = glyph->bbox_exact.midpoint().x();
    auto center = w / 2;

    if (params.draw_metrics) {
        auto& color = params.line_color;
        ctx->set_source_rgba(color.get_red(), color.get_green(), color.get_blue(), color.get_alpha());
        ctx->set_line_width(1.0 / font_size);

        std::array lines = {
            font->GetBaselines()[SP_CSS_BASELINE_AUTO],
            font->GetTypoAscent(),
            -font->GetTypoDescent()
        };
        for (double y : lines) {
            ctx->move_to(0, y);
            ctx->line_to(w, y);
            ctx->stroke();
        }

        auto adv = glyph->h_advance / 2;
        std::array vert = {
            center - adv,
            center + adv,
        };
        for (double x : vert) {
            ctx->move_to(x, -1);
            ctx->line_to(x, +1);
            ctx->stroke();
        }
    }

    ctx->translate(center - midpoint, 0);
    feed_pathvector_to_cairo(ctx->cobj(), glyph->pathvector);
    auto& fg = params.glyph_color;
    ctx->set_source_rgb(fg.get_red(), fg.get_green(), fg.get_blue());
    ctx->fill();

    ctx->restore();
}

} // namespace
