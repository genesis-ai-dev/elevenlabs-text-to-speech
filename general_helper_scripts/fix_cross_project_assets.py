#!/usr/bin/env python3
"""
Fix cross-project asset links created by previous runs.

Actions:
- Detect quest_asset_link rows that connect a quest to an asset already used by other projects.
- For each, create/find a project-scoped duplicate asset with the same name and move the quest link to it.
- For asset_content_link:
  - Default: copy project's source-language rows from the old asset to the new asset (optionally remove the old rows if created in sessions).
  - With --move-session-links and one or more --session-file: update rows created in those sessions to point to the new asset (no duplicates left behind).
- For asset_tag_link: copy to the new asset (non-destructive by default).

By default runs in dry-run mode. Use --apply to write changes.
You can pass --session-file multiple times.
"""

import os
import json
import argparse
from typing import Dict, Any, List, Optional, Set, Tuple, DefaultDict
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv

from unified_content_handlers.supabase_handler import SupabaseHandler


def load_sessions(session_files: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not session_files:
        return []
    sessions = []
    for p in session_files:
        with open(p, 'r', encoding='utf-8') as f:
            sessions.append(json.load(f))
    return sessions


def build_session_index(sessions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Set[str]]]:
    """
    Build an index of session-created links for quick lookup.
    Returns dict with keys:
      - 'asset_content': mapping old_asset_id -> set(source_language_id)
      - 'asset_tag': mapping old_asset_id -> set(tag_id)
    """
    asset_content: DefaultDict[str, Set[str]] = defaultdict(set)
    asset_tag: DefaultDict[str, Set[str]] = defaultdict(set)
    for sess in sessions:
        for rec in sess.get('asset_content_links', []) or []:
            aid = rec.get('asset_id')
            lang = rec.get('source_language_id')
            if aid and lang:
                asset_content[aid].add(lang)
        for rec in sess.get('asset_tag_links', []) or []:
            aid = rec.get('asset_id')
            tid = rec.get('tag_id')
            if aid and tid:
                asset_tag[aid].add(tid)
    return {'asset_content': asset_content, 'asset_tag': asset_tag}


def get_project_source_language_ids(sb: SupabaseHandler, project_id: str) -> List[str]:
    # Prefer project_language_link 'source' entries
    q = sb.client.table('project_language_link') \
        .select('language_id') \
        .eq('project_id', project_id) \
        .eq('language_type', 'source')
    q = sb.execute_with_retry(q)
    langs = [row['language_id'] for row in (q.data or [])]
    if langs:
        return langs
    # Fallback to legacy project.source_language_id
    p = sb.client.table('project') \
        .select('source_language_id') \
        .eq('id', project_id)
    p = sb.execute_with_retry(p)
    if p.data and p.data[0].get('source_language_id'):
        return [p.data[0]['source_language_id']]
    return []


def list_cross_project_quest_asset_links(sb: SupabaseHandler) -> List[Dict[str, Any]]:
    # Fetch all quest_asset_link with quest.project_id
    qal = sb.client.table('quest_asset_link') \
        .select('quest_id,asset_id,quest:quest_id(project_id)')
    qal = sb.execute_with_retry(qal)
    results: List[Dict[str, Any]] = []
    for row in qal.data or []:
        quest_id = row['quest_id']
        asset_id = row['asset_id']
        project_id = row['quest']['project_id']
        linked_projects = sb.get_asset_linked_project_ids(asset_id)
        # Cross-project if this asset is linked to any other project than this quest's project
        if linked_projects and (len(set(linked_projects)) > 1 or (linked_projects and linked_projects[0] != project_id)):
            results.append({
                'quest_id': quest_id,
                'asset_id': asset_id,
                'project_id': project_id,
                'linked_projects': linked_projects,
            })
    return results


def list_cross_project_assets_for_project(sb: SupabaseHandler, project_id: str) -> List[Dict[str, Any]]:
    """Project-scoped detection following the requested logic:
    - All quests in the project
    - All quest_asset_link for those quests -> collect asset_ids
    - For those asset_ids, find any quest_asset_link rows where the quest belongs to a different project
    Returns entries aggregated per asset with our quest_ids and the set of other project_ids.
    """
    # Quests for this project
    q = sb.client.table('quest').select('id').eq('project_id', project_id)
    q = sb.execute_with_retry(q)
    quest_ids = [row['id'] for row in (q.data or [])]
    if not quest_ids:
        return []

    # Helper to chunk large IN() lists to avoid 414 URI too large
    def chunks(seq: List[str], size: int = 200):
        for i in range(0, len(seq), size):
            yield seq[i:i+size]

    # Links for our quests (chunked)
    by_asset: DefaultDict[str, Set[str]] = defaultdict(set)
    for qchunk in chunks(quest_ids):
        qal = sb.client.table('quest_asset_link').select('quest_id,asset_id').in_('quest_id', qchunk)
        qal = sb.execute_with_retry(qal)
        for row in qal.data or []:
            by_asset[row['asset_id']].add(row['quest_id'])
    if not by_asset:
        return []

    asset_ids = list(by_asset.keys())
    # All links for those assets (across all projects), chunked
    per_asset: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for achunk in chunks(asset_ids):
        all_links = sb.client.table('quest_asset_link').select('quest_id,asset_id,quest:quest_id(project_id)').in_('asset_id', achunk)
        all_links = sb.execute_with_retry(all_links)
        for row in all_links.data or []:
            per_asset[row['asset_id']].append(row)

    issues: List[Dict[str, Any]] = []
    for asset_id, rows in per_asset.items():
        projects_involved = {r['quest']['project_id'] for r in rows}
        if len(projects_involved) <= 1:
            continue
        # If any row is not our project, then this asset is cross-project
        if any(r['quest']['project_id'] != project_id for r in rows):
            our_quest_ids = [r['quest_id'] for r in rows if r['quest']['project_id'] == project_id]
            other_projects = sorted({r['quest']['project_id'] for r in rows if r['quest']['project_id'] != project_id})
            issues.append({
                'asset_id': asset_id,
                'project_id': project_id,
                'our_quest_ids': our_quest_ids,
                'linked_projects': other_projects,
            })
    return issues


def copy_or_move_content_links_for_project(
    sb: SupabaseHandler,
    old_asset_id: str,
    new_asset_id: str,
    project_id: str,
    session_index: Dict[str, Dict[str, Set[str]]],
    apply_changes: bool,
    remove_old_if_in_session: bool = True,
    move_session_links: bool = False,
) -> Tuple[int, int]:
    """Copy or move asset_content_link rows for the project's source languages from old asset to new asset.
    If move_session_links is True, and sessions are provided, update rows created in sessions in-place to point to new asset.
    Returns (copied_or_moved_count, removed_count)."""
    copied = 0
    removed = 0
    source_lang_ids = get_project_source_language_ids(sb, project_id)
    if not source_lang_ids:
        return copied, removed

    # If moving session-created links, update in place for those language_ids
    if move_session_links and session_index:
        session_langs = session_index['asset_content'].get(old_asset_id, set())
        langs_to_move = sorted(set(source_lang_ids).intersection(session_langs))
        if langs_to_move and apply_changes:
            # Update all matching rows to point to the new asset
            upd = sb.client.table('asset_content_link') \
                .update({'asset_id': new_asset_id, 'last_updated': datetime.now(timezone.utc).isoformat()}) \
                .eq('asset_id', old_asset_id) \
                .in_('source_language_id', langs_to_move)
            sb.execute_with_retry(upd)
        copied += len(langs_to_move)
        # No removals needed in move mode
        return copied, removed

    # Else: copy mode
    for lang_id in source_lang_ids:
        q = sb.client.table('asset_content_link') \
            .select('id,text,audio_id') \
            .eq('asset_id', old_asset_id) \
            .eq('source_language_id', lang_id)
        q = sb.execute_with_retry(q)
        if not q.data:
            continue
        row = q.data[0]
        text = row['text']
        audio_id = row.get('audio_id')
        if apply_changes:
            sb.upsert_asset_content_link(new_asset_id, text, source_language_id=lang_id, audio_id=audio_id)
        copied += 1

        if apply_changes and remove_old_if_in_session and session_index:
            session_langs = session_index['asset_content'].get(old_asset_id, set())
            if lang_id in session_langs:
                delb = sb.client.table('asset_content_link') \
                    .delete() \
                    .eq('id', row['id'])
                sb.execute_with_retry(delb)
                removed += 1

    return copied, removed


def copy_tag_links(
    sb: SupabaseHandler,
    old_asset_id: str,
    new_asset_id: str,
    session_index: Dict[str, Dict[str, Set[str]]],
    apply_changes: bool,
    remove_old_if_in_session: bool = False,
) -> Tuple[int, int]:
    """Copy asset_tag_link from old asset to new asset.
    If session provided, prefer only tags listed in session; otherwise copy all.
    Returns (copied_count, removed_count)."""
    copied = 0
    removed = 0

    session_tag_ids = set()
    if session_index:
        session_tag_ids = session_index['asset_tag'].get(old_asset_id, set())
    if session_tag_ids:
        tag_ids = list(session_tag_ids)
    else:
        q = sb.client.table('asset_tag_link') \
            .select('tag_id') \
            .eq('asset_id', old_asset_id)
        q = sb.execute_with_retry(q)
        tag_ids = [row['tag_id'] for row in (q.data or [])]

    for tag_id in tag_ids:
        if apply_changes:
            sb.upsert_asset_tag_link(new_asset_id, tag_id)
        copied += 1

        if apply_changes and remove_old_if_in_session and session_index:
            if tag_id in session_tag_ids:
                delb = sb.client.table('asset_tag_link') \
                    .delete() \
                    .eq('asset_id', old_asset_id) \
                    .eq('tag_id', tag_id)
                sb.execute_with_retry(delb)
                removed += 1

    return copied, removed


def move_session_tag_links(
    sb: SupabaseHandler,
    old_asset_id: str,
    new_asset_id: str,
    session_index: Dict[str, Dict[str, Set[str]]],
    apply_changes: bool,
) -> int:
    """Move (update) asset_tag_link rows created in sessions from old asset to new asset.
    Returns number of moved rows."""
    if not apply_changes:
        return 0
    session_tag_ids = session_index.get('asset_tag', {}).get(old_asset_id, set())
    if not session_tag_ids:
        return 0
    upd = sb.client.table('asset_tag_link') \
        .update({'asset_id': new_asset_id, 'last_modified': datetime.now(timezone.utc).isoformat()}) \
        .eq('asset_id', old_asset_id) \
        .in_('tag_id', list(session_tag_ids))
    sb.execute_with_retry(upd)
    return len(session_tag_ids)


def replace_quest_asset_link(sb: SupabaseHandler, quest_id: str, old_asset_id: str, new_asset_id: str, apply_changes: bool) -> None:
    if not apply_changes:
        return
    # Insert new link (idempotent via upsert helper)
    sb.upsert_quest_asset_link(quest_id, new_asset_id)
    # Delete old link
    delb = sb.client.table('quest_asset_link') \
        .delete() \
        .eq('quest_id', quest_id) \
        .eq('asset_id', old_asset_id)
    sb.execute_with_retry(delb)


def main():
    parser = argparse.ArgumentParser(description='Fix cross-project asset links and migrate content/tags.')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run).')
    parser.add_argument('--session-file', action='append', help='Optional path(s) to session_record_*.json to guide selective moves/removals.')
    parser.add_argument('--project-name', help='Optional project name filter to only fix links for this project.')
    parser.add_argument('--move-session-links', action='store_true', help='Move session-created asset_content_link rows to the new asset instead of copying.')
    parser.add_argument('--move-session-tags', action='store_true', help='Move session-created asset_tag_link rows to the new asset instead of copying.')
    args = parser.parse_args()

    load_dotenv()
    sb = SupabaseHandler()

    sessions = load_sessions(args.session_file)
    session_index = build_session_index(sessions)

    # Optional project filter mapping name->id
    project_id_filter: Optional[str] = None
    if args.project_name:
        q = sb.client.table('project').select('id').eq('name', args.project_name)
        q = sb.execute_with_retry(q)
        if not q.data:
            raise SystemExit(f"Project not found: {args.project_name}")
        project_id_filter = q.data[0]['id']

    # Use project-scoped detection if a project filter is provided; else use global detection
    if project_id_filter:
        issues = list_cross_project_assets_for_project(sb, project_id_filter)
    else:
        issues = list_cross_project_quest_asset_links(sb)

    print(f"Found {len(issues)} cross-project quest-asset links{f' for project {args.project_name}' if args.project_name else ''}.")
    total_copied_content = 0
    total_removed_content = 0
    total_copied_tags = 0
    total_removed_tags = 0

    for item in issues:
        old_asset_id = item['asset_id']
        project_id = item['project_id']
        asset_name = sb.get_asset_name_by_id(old_asset_id) or '<unknown>'
        new_asset_id = sb.get_or_create_project_scoped_asset(asset_name, project_id)

        print(f"- Asset {old_asset_id} ('{asset_name}') used across projects {item['linked_projects']} -> project {project_id} uses {new_asset_id}")

        # Move all quest links in this project from old asset to new asset
        for quest_id in item.get('our_quest_ids', []):
            replace_quest_asset_link(sb, quest_id, old_asset_id, new_asset_id, args.apply)

        # Copy content for this project's source languages
        copied, removed = copy_or_move_content_links_for_project(
            sb, old_asset_id, new_asset_id, project_id, session_index, apply_changes=args.apply,
            remove_old_if_in_session=True, move_session_links=args.move_session_links,
        )
        total_copied_content += copied
        total_removed_content += removed

        # Copy tag links (do not remove by default)
        if args.move_session_tags:
            moved_t = move_session_tag_links(sb, old_asset_id, new_asset_id, session_index, apply_changes=args.apply)
            total_copied_tags += moved_t
        else:
            copied_t, removed_t = copy_tag_links(
                sb, old_asset_id, new_asset_id, session_index, apply_changes=args.apply,
                remove_old_if_in_session=False,
            )
            total_copied_tags += copied_t
            total_removed_tags += removed_t

        # Rebuild closures for project
        if args.apply:
            try:
                sb.rebuild_project_closure(project_id)
            except Exception:
                pass

    print(f"Summary: copied_content={total_copied_content}, removed_content={total_removed_content}, copied_tags={total_copied_tags}, removed_tags={total_removed_tags}")
    if not args.apply:
        print("Dry-run complete. Re-run with --apply to perform changes.")


if __name__ == '__main__':
    main()


