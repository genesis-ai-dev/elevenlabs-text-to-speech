#!/usr/bin/env python3
import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from ScriptureReference import ScriptureReference  # your class for pulling verses

def get_supabase_client():
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in your .env")
    return create_client(url, key)

def upsert_language(sb: Client, lang):
    """Upsert a language and return its ID."""
    # Check if language exists
    resp = sb.table('language') \
        .select('id') \
        .eq('iso639_3', lang['iso639_3']) \
        .execute()
    
    if resp.data:
        return resp.data[0]['id']
        
    # If not exists, insert
    resp = sb.table('language') \
        .insert({
            'native_name': lang['native_name'],
            'english_name': lang['english_name'],
            'iso639_3': lang['iso639_3'],
            'locale': lang['locale'],
            'ui_ready': lang['ui_ready']
        }, returning='representation') \
        .execute()
    return resp.data[0]['id']

def upsert_project(sb: Client, proj, lang_map):
    """Upsert a project and return its ID."""
    # Check if project exists
    resp = sb.table('project') \
        .select('id') \
        .eq('name', proj['name']) \
        .eq('source_language_id', lang_map[proj['source_language_english_name']]) \
        .eq('target_language_id', lang_map[proj['target_language_english_name']]) \
        .execute()
    
    if resp.data:
        return resp.data[0]['id']
        
    # If not exists, insert
    resp = sb.table('project') \
        .insert({
            'name': proj['name'],
            'description': proj.get('description', ''),
            'source_language_id': lang_map[proj['source_language_english_name']],
            'target_language_id': lang_map[proj['target_language_english_name']]
        }, returning='representation') \
        .execute()
    return resp.data[0]['id']

def get_or_create_tag(sb: Client, cache: dict, tag_name: str):
    """Get or create a tag by name, cache and return its ID."""
    if tag_name in cache:
        return cache[tag_name]
        
    # Check if tag exists
    resp = sb.table('tag') \
        .select('id') \
        .eq('name', tag_name) \
        .execute()
    
    if resp.data:
        tag_id = resp.data[0]['id']
        cache[tag_name] = tag_id
        return tag_id
        
    # If not exists, insert
    resp = sb.table('tag') \
        .insert({'name': tag_name}, returning='representation') \
        .execute()
    tag_id = resp.data[0]['id']
    cache[tag_name] = tag_id
    return tag_id

def main():
    sb = get_supabase_client()
    with open('test_quests.json', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Languages
    lang_map = {}
    for lang in data['languages']:
        lang_id = upsert_language(sb, lang)  # :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}
        lang_map[lang['english_name']] = lang_id

    # Fetch any project languages not in JSON from the DB
    for proj in data['projects']:
        for lang_name in (proj['source_language_english_name'], proj['target_language_english_name']):
            if lang_name not in lang_map:
                resp = sb.table('language') \
                    .select('id') \
                    .eq('english_name', lang_name) \
                    .execute()
                if not resp.data:
                    raise RuntimeError(f"Language {lang_name} not found in DB")
                lang_map[lang_name] = resp.data[0]['id']

    # 2. Projects & Quests
    tag_cache = {}
    for proj in data['projects']:
        project_id = upsert_project(sb, proj, lang_map)

        for quest in proj['quests']:
            # Upsert quest
            qresp = sb.table('quest') \
                .upsert({
                    'name': quest['name'],
                    'description': quest.get('description', ''),
                    'project_id': project_id
                }, returning='representation') \
                .execute()
            quest_id = qresp.data[0]['id']

            # For collecting quest-level book/chapter tags
            all_books = set()
            all_chapters = set()

            # 3. Assets & Content & Quest-Asset Links & Asset Tags
            for start_ref, end_ref in quest.get('verse_ranges', []):
                sr = ScriptureReference(start_ref, end_ref, "eng-engwebp")
                for verse_ref, verse_text in sr.verses:
                    # Check if asset exists
                    aresp = sb.table('asset') \
                        .select('id') \
                        .eq('name', verse_ref) \
                        .eq('source_language_id', lang_map[proj['source_language_english_name']]) \
                        .execute()
                    
                    if aresp.data:
                        asset_id = aresp.data[0]['id']
                    else:
                        # If not exists, insert
                        aresp = sb.table('asset') \
                            .insert({
                                'name': verse_ref,
                                'source_language_id': lang_map[proj['source_language_english_name']]
                            }, returning='representation') \
                            .execute()
                        asset_id = aresp.data[0]['id']

                    # Content link
                    sb.table('asset_content_link') \
                        .upsert({
                            'asset_id': asset_id,
                            'text': verse_text
                        }) \
                        .execute()

                    # Quest–Asset link
                    sb.table('quest_asset_link') \
                        .upsert({
                            'quest_id': quest_id,
                            'asset_id': asset_id
                        }) \
                        .execute()

                    # Parse tags from verse_ref: e.g. "GEN_1_1"
                    book_code, chapter, verse = verse_ref.split('_', 2)
                    all_books.add(book_code)
                    all_chapters.add(chapter)

                    # Asset-level tags: book, chapter, verse
                    for tag_name in (
                        f"book:{book_code}",
                        f"chapter:{chapter}",
                        f"verse:{verse}"
                    ):
                        tag_id = get_or_create_tag(sb, tag_cache, tag_name)
                        sb.table('asset_tag_link') \
                            .upsert({
                                'asset_id': asset_id,
                                'tag_id': tag_id
                            }) \
                            .execute()

            # 4. Quest-level tags (only if single book)
            if len(all_books) == 1:
                bc = next(iter(all_books))
                bid = get_or_create_tag(sb, tag_cache, f"book:{bc}")
                sb.table('quest_tag_link') \
                    .upsert({'quest_id': quest_id, 'tag_id': bid}) \
                    .execute()

                if len(all_chapters) == 1:
                    ch = next(iter(all_chapters))
                    cid = get_or_create_tag(sb, tag_cache, f"chapter:{ch}")
                    sb.table('quest_tag_link') \
                        .upsert({'quest_id': quest_id, 'tag_id': cid}) \
                        .execute()

if __name__ == "__main__":
    main()
