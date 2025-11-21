// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * This file contains the font collection related logic. The functions to manage the font
 * collections are defined in this file.
 *
 * Authors:
 *   Vaibhav Malik <vaibhavmalik2018@gmail.com>
 *
 * The contents of this file may be used under the GNU General Public License Version 2 or later.
 *
 */

#include "font-collections.h"

#include <fstream>
// #include <iostream>
#include <gtkmm.h>

#include "io/resource.h"
#include "io/dir-util.h"
#include "libnrtype/font-lister.h"

using namespace Inkscape::IO::Resource;

namespace Inkscape {

// Function to manage the singleton instance.
FontCollections* FontCollections::get()
{
    static FontCollections* s_instance = new Inkscape::FontCollections();
    return s_instance;
}

FontCollections::FontCollections()
{
    init();
}

void FontCollections::init()
{
    // Step 1: Get the collections directory.
    Glib::ustring directory = get_path_string(USER, FONTCOLLECTIONS, "");

    // Create the fontcollections directory if not already present.
    // This should be called only once.
    static bool build_dir = true;

    if(build_dir) {
#ifdef _WIN32
        mkdir(directory.c_str());
#else
        mkdir(directory.c_str(), S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH);
#endif
        build_dir = false;
    }

    // Clear the previous collections(we may be re-reading).
    clear();

    // Step 2: Get the names of the files present in this directory.
    std::vector<const char *> allowed_user_ext = {"txt"};
    std::vector<const char *> allowed_system_ext = {"log"};
    std::vector<std::string> user_files = {};
    std::vector<std::string> system_files = {};
    Inkscape::IO::Resource::get_filenames_from_path(user_files, directory, allowed_user_ext,
                                                    (std::vector<const char *>){});
    Inkscape::IO::Resource::get_filenames_from_path(system_files, directory, allowed_system_ext,
                                                    (std::vector<const char *>){});

    // Step 3: Recursively read the contents of the files,
    // and load the collections into the map.
    read(system_files, true);
    read(user_files);

    add_system_collections();
}

// Clear all collections
void FontCollections::clear()
{
    // Write code to clear the collections
    _user_collections.clear();
    _system_collections.clear();
}

/*
void FontCollections::print_collection_font_map()
{
    std::cout << "User collections" << std::endl;
    for(auto const &col: _user_collections) {
        std::cout << col.name << std::endl;

        for(auto const &font: col.fonts) {
            std::cout << "\t" << font << std::endl;
        }
    }

    std::cout << "System collections" << std::endl;
    for(auto const &col: _system_collections) {
        std::cout << col.name << std::endl;

        for(auto const &font: col.fonts) {
            std::cout << "\t" << font << std::endl;
        }
    }
}
*/

// Read collections files.
void FontCollections::read(std::vector<std::string> const &files, bool const is_system)
{
    // Iterate over the files vector and read each file.
    for(auto const &file: files) {
        _read(file, is_system);
    }
}

// Read fonts stored in a collection file.
void FontCollections::_read(std::string const &file, bool const is_system)
{
    // Filestream object to read data from the file.
    std::ifstream input_file(file);

    // Check if the file is open or not.
    if (input_file.is_open()) {
        // Generate the collection name from the file name.
        Glib::ustring path = get_path_string(USER, FONTCOLLECTIONS, "");

        Glib::ustring collection_name = file.substr(path.length() + 1, file.length() - path.length() - 5);
        std::string line;

        // Now read all the fonts stored in this file.
        std::set<Glib::ustring> fonts;
        Inkscape::FontLister *font_lister = Inkscape::FontLister::get_instance();

        while (getline(input_file, line)) {
            // Get rid of unwanted characters from the left and right.
            line = trim_left_and_right(line);
            Glib::ustring font = line;

            // Now check if the font is installed on the system because it is possible
            // that a previously installed font may not be available now.
            if (font_lister->font_installed_on_system(font)) {
                fonts.insert(font);
            }
        }

        // Important: Close the file after use!
        input_file.close();

        // Now insert these fonts into the font collections.
        FontCollection temp_col(collection_name, fonts, is_system);

        if (is_system) {
            _system_collections.insert(temp_col);
        } else {
            _user_collections.insert(temp_col);
        }
    } else {
        // Error: Failed to open the file.
        // std::cout << "Failed to open file: " << file << std::endl;
    }
}

// Function to write a collection to file.
void FontCollections::write_collection(const Glib::ustring& collection_name, const std::set <Glib::ustring>& fonts, bool is_system)
{
    std::string collection_file = generate_filename_from_collection(collection_name, is_system);
    std::fstream output_file;
    output_file.open(collection_file, std::fstream::out);

    // Check if the file opened or not.
    if (output_file.is_open()) {
        // Insert the fonts into the file.
        for (auto const &font : fonts) {
            output_file << font << '\n';
        }

        // Very Important: Close the file after use.
        output_file.close();
        init();
    } else {
        // Error: Failed to open the file.
        // std::cout << "Failed to open file: " << collection_file << std::endl;
    }
}

// System collections.
void FontCollections::add_system_collections()
{
    // clear the vector, we may be re-reading.
    _system_collections.clear();

    // System collections:
    // 1. Document fonts.
    // 2. Recently Used fonts.
    std::string col_name = DOCUMENT_FONTS;
    FontCollection temp_col1(col_name, true);
    col_name = RECENTLY_USED_FONTS;
    FontCollection temp_col2(col_name, true);
    _system_collections.insert(temp_col1);
    _system_collections.insert(temp_col2);
}

// Add a collection.
void FontCollections::add_collection(const Glib::ustring& collection_name, bool is_system)
{
    // Check for empty name.
    if (collection_name == "") {
        return;
    }

    // Get rid of unwanted characters from left and right.
    std::string col_name_copy = collection_name;
    col_name_copy = trim_left_and_right(col_name_copy);
    FontCollection temp_col(col_name_copy, is_system);

    if (is_system) {
        // Add and save this collection as a system collection.
        // No need to save system collections in a file,
        // because system collections are already being managed
        // by separate files.
        _system_collections.insert(temp_col);
    } else {
        // The return value will tell if the collection was already present
        // in the set or not.
        auto ret_val = _user_collections.insert(temp_col);

        // Write the changes only if the collection was inserted.
        if (ret_val.second == true) {
            // write this collection to a file.
            write_collection(col_name_copy, temp_col.fonts);
        }
    }

    update_signal.emit();
}

// Remove a collection. Only user collections are allowed to be removed.
void FontCollections::remove_collection(const Glib::ustring& collection_name)
{
    // Check if the collection is there.
    FontCollection temp_col(collection_name, false);
    auto it = _user_collections.find(temp_col);

    if (it != _user_collections.end()) {
        // Collection exists, erase it from user and selected collections.
        _user_collections.erase(it);

        Glib::ustring file_name = collection_name + ".txt";
        std::string collection_file = get_path_string(USER, FONTCOLLECTIONS, file_name.c_str());
        // std::cout << "Deleting: " << collection_file << std::endl;

        // Erase the collection file from the folder.
        remove(collection_file.c_str());

        // Emit the update signal to update the popover list in:
        // (i) T and F dialog
        // (ii) Text Toolbar
        update_signal.emit();
    } else {
        return;
    }

    // Check if the collection was selected.
    auto it1 = _selected_collections.find(collection_name);

    if (it1 != _selected_collections.end()) {
        // Remove it from the selected collections,
        // and emit the selection update signal.
        _selected_collections.erase(it1);

        // Update the font list accordingly.
        Inkscape::FontLister::get_instance()->apply_collections(_selected_collections);

        // Let the world know.
        selection_update_signal.emit();
    }
}

// Only user collections can be renamed.
void FontCollections::rename_collection(const Glib::ustring& old_name, const Glib::ustring &new_name)
{
    if (old_name == new_name) {
        return;
    }

    // 1. Copy the fonts stored under old_name.
    FontCollection old_col(old_name, false);
    std::set <Glib::ustring> fonts = get_fonts(old_name);

    // 2. Remove the old collection from the map.
    auto it = _user_collections.find(old_col);

    // Only if it exists
    if (it != _user_collections.end()) {
        _user_collections.erase(it);

        // 3. Rename the file.
        Glib::ustring old_file = old_name + ".txt";
        Glib::ustring new_file = new_name + ".txt";
        std::string old_file_path = get_path_string(USER, FONTCOLLECTIONS, old_file.c_str());
        std::string new_file_path = get_path_string(USER, FONTCOLLECTIONS, new_file.c_str());
        rename(old_file_path.c_str(), new_file_path.c_str());

        // 4: Insert new_collection into the map.
        FontCollection new_col(new_name, fonts, false);
        _user_collections.insert(new_col);

        // Check if it was selected before renaming or not.
        auto it1 = _selected_collections.find(old_name);

        if (it1 != _selected_collections.end()) {
            // Select the renamed collection.
            _selected_collections.insert(new_name);

            // No need to update the font list,
            // as the fonts under selection remains the same.
            // Emit the selection update signal.
            selection_update_signal.emit();
        }
    } else {
        // Otherwise, add it as a new collection.
        add_collection(new_name);
    }

    // Update the popover lists.
    update_signal.emit();
}

void FontCollections::rename_font(const Glib::ustring& collection_name, const Glib::ustring &old_name, const Glib::ustring &new_name)
{
    // 1. Erase the old font.
    remove_font(collection_name, old_name);

    // 2. Add the new font into the collection.
    add_font(collection_name, new_name);
}

// Add a font to a collection and save that collection.
void FontCollections::add_font(const Glib::ustring& collection_name, const Glib::ustring& font_name)
{
    // std::cout << "Collection: " << collection_name << ", Font: " << font_name <<std::endl;

    if (font_name == "" || collection_name == "") {
        return;
    }

    // First search the collection.
    FontCollection temp_col(collection_name, false);
    auto node = _user_collections.extract(temp_col);

    if (node && !node.empty()) {
        node.value().insert_font(font_name);
        std::set <Glib::ustring> fonts = node.value().fonts;
        _user_collections.insert(std::move(node));

        write_collection(collection_name, fonts);

        // Update the font list if the collection was already selected.
        auto it = _selected_collections.find(collection_name);

        if (it != _selected_collections.end()) {
            // No need to send the update signal as the font list will be changed
            // here only. No other widget is required to take any action.
            Inkscape::FontLister::get_instance()->apply_collections(_selected_collections);
        }
    }

    update_signal.emit();
}

// Remove a font.
void FontCollections::remove_font(const Glib::ustring& collection_name, const Glib::ustring& font_name)
{
    if (font_name == "" || collection_name == "") {
        return;
    }

    // 1. Check if the font is present in the set
    FontCollection temp_col(collection_name, false);
    auto node = _user_collections.extract(temp_col);

    // 2. Delete the font if it exists.
    if (node) {
        node.value().fonts.erase(font_name);
        std::set <Glib::ustring> fonts = node.value().fonts;
        _user_collections.insert(std::move(node));

        // Save the changes to the collection file.
        write_collection(collection_name, fonts);

        // Update the font list if the collection was already selected.
        auto it = _selected_collections.find(collection_name);

        if (it != _selected_collections.end()) {
            // No need to send the update signal as the font list will be changed
            // here only. No other widget is required to take any action.
            Inkscape::FontLister::get_instance()->apply_collections(_selected_collections);
        }
    }

    update_signal.emit();
}

void FontCollections::update_selected_collections(const Glib::ustring& collection_name)
{
    auto it = _selected_collections.find(collection_name);

    if (it != _selected_collections.end()) {
        // Collection already present in the selected collections.
        // Remove it.
        _selected_collections.erase(it);
    } else {
        _selected_collections.insert(collection_name);
    }

    // Re-generate the font list.
    Inkscape::FontLister::get_instance()->apply_collections(_selected_collections);

    // Emit the selection update signal.
    selection_update_signal.emit();
}

bool FontCollections::is_collection_selected(const Glib::ustring& collection_name)
{
    auto it = _selected_collections.find(collection_name);

    if(it != _selected_collections.end()) {
        return true;
    }

    return false;
}

void FontCollections::clear_selected_collections()
{
    _selected_collections.clear();

    // Emit the selection update signal.
    selection_update_signal.emit();
}

// Removes unwanted characters from the left and right of the string.
std::string& FontCollections::trim_left_and_right(std::string& s, const char* t)
{
    s.erase(0, s.find_first_not_of(t));
    s.erase(s.find_last_not_of(t) + 1);
    return s;
}

int FontCollections::get_user_collection_location(const Glib::ustring& collection_name)
{
    // This is a binary-search function on the elements of a set.
    std::vector <Glib::ustring> collections(_user_collections.size());

    // Copy the elements of the set in a vector.
    int i = 0;
    for(auto const &collection: _user_collections) {
        collections[i++] = collection.name;
    }

    return std::lower_bound(collections.begin(), collections.end(), collection_name) - collections.begin();
}

std::string FontCollections::generate_filename_from_collection(const Glib::ustring &collection_name, bool is_system)
{
    Glib::ustring file_name;
    std::string collection_file;

    if(is_system) {
        file_name = collection_name + ".log";
    } else {
        file_name = collection_name + ".txt";
    }

    collection_file = get_path_string(USER, FONTCOLLECTIONS, file_name.c_str());

    return collection_file;
}

int FontCollections::get_collections_count(bool is_system) const
{
    if(is_system) {
        return _system_collections.size();
    }

    return _user_collections.size();
}

int FontCollections::get_selected_collections_count() const
{
    return _selected_collections.size();
}

bool FontCollections::find_collection(Glib::ustring const &collection_name, bool is_system) const
{
    FontCollection temp_collection(collection_name, is_system);

    if (is_system) {
        auto it = _system_collections.find(temp_collection);

        if (it != _system_collections.end()) {
            return true;
        }
    } else {
        auto it = _user_collections.find(temp_collection);

        if (it != _user_collections.end()) {
            return true;
        }
    }

    return false;
}

// Get a set of the collections.
std::vector<Glib::ustring> FontCollections::get_collections(bool is_system) const
{
    std::vector <Glib::ustring> collections;
    if(is_system) {
        for(auto const &col: _system_collections) {
            collections.push_back(col.name);
        }
    } else {
        for(auto const &col: _user_collections) {
            collections.push_back(col.name);
        }
    }

    return collections;
}

// Get all of the collections.
std::vector<Glib::ustring> FontCollections::get_all_collections() const
{
    std::vector <Glib::ustring> collections(_system_collections.size() + _user_collections.size());

    // Iterate over all the key value pairs and
    // Insert them into the set.
    int i = 0;

    for(auto const &col: _system_collections) {
        collections[i++] = col.name;
    }

    for(auto const &col: _user_collections) {
        collections[i++] = col.name;
    }

    return collections;
}

// Get the set of fonts stored in a particular collection.
std::set<Glib::ustring> const &FontCollections::get_fonts(const Glib::ustring& collection_name, bool is_system) const
{
    // Check if the collection exists.
    FontCollection temp_col(collection_name, is_system);
    auto it = _user_collections.find(temp_col);
    if(it != _user_collections.end()) {
        // The collection exists.
        return (*it).fonts;
    }

    static std::set<Glib::ustring> empty_set;
    return empty_set;
}

bool FontCollections::is_font_in_collection(const Glib::ustring& collection_name, const Glib::ustring& font_name) const {
    auto& set = get_fonts(collection_name);
    return set.contains(font_name);
}

const std::set<Glib::ustring>& FontCollections::get_selected_collections() const {
    return _selected_collections;
}

} // Namespace

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
