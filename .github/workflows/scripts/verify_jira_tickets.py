#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import List, Set, Dict
import requests
from requests.auth import HTTPBasicAuth

def extract_jira_tickets_from_release_notes(release_body: str) -> Set[str]:
    """リリースノートからJIRAチケット番号を抽出"""
    pattern = r'\[?(WOR-\d+)\]?'
    tickets = re.findall(pattern, release_body)
    return set(tickets)

def format_release_note_title(title: str) -> str:
    """リリースノートのタイトルをフォーマット
    - 'by @username' を削除
    - PR URLを <url|#123> 形式に変換
    """
    # 'by @username' を削除
    title = re.sub(r'\s+by\s+@[\w-]+\s*$', '', title)
    
    # PR URLを検出して変換
    # https://github.com/org/repo/pull/123 -> <https://github.com/org/repo/pull/123|#123>
    pr_pattern = r'in\s+(https://github\.com/[\w-]+/[\w-]+/pull/(\d+))'
    match = re.search(pr_pattern, title)
    if match:
        full_url = match.group(1)
        pr_number = match.group(2)
        # Slack形式のリンクに置換
        title = title[:match.start()] + f'in <{full_url}|#{pr_number}>'
    
    return title.strip()

def extract_tickets_with_titles_from_release_notes(release_body: str) -> Dict[str, str]:
    """リリースノートからJIRAチケット番号とタイトルを抽出
    Returns: {ticket_number: title} の辞書
    """
    ticket_titles = {}
    lines = release_body.split('\n')
    
    for line in lines:
        # チケット番号を含む行を探す
        match = re.search(r'\[?(WOR-\d+)\]?', line)
        if match:
            ticket = match.group(1)
            # チケット番号の後の部分をタイトルとして抽出（]の後から行末まで）
            title_start = match.end()
            if ']' in line[match.start():]:
                # [WOR-XXXX] 形式の場合
                bracket_pos = line.find(']', match.start())
                title_start = bracket_pos + 1
            
            # タイトル部分を取得してクリーンアップ
            title = line[title_start:].strip()
            # 先頭の記号やスペースを除去
            title = re.sub(r'^[\s\-\*\:]+', '', title).strip()
            
            if title:
                # フォーマット処理
                title = format_release_note_title(title)
                ticket_titles[ticket] = title
            else:
                ticket_titles[ticket] = '(タイトルなし)'
    
    return ticket_titles


def extract_fix_version_from_jira_link(release_body: str) -> str:
    """リリースノート内のJIRAリンクからfix versionを抽出
    例: https://omnisinc.atlassian.net/projects/WOR/versions/11038/tab/release-report-all-issues -> 11038
    """
    # JIRAバージョンリンクのパターンを検索
    pattern = r'https://omnisinc\.atlassian\.net/projects/\w+/versions/(\d+)'
    match = re.search(pattern, release_body)
    if match:
        return match.group(1)
    return ''

def get_jira_tickets_from_api(fix_version: str) -> Set[str]:
    """JIRA APIからfix versionに紐づくチケットを取得"""
    jira_email = os.environ.get('JIRA_EMAIL')
    jira_api_token = os.environ.get('JIRA_API_TOKEN')
    
    if not all([jira_email, jira_api_token]):
        print("Error: JIRA credentials not found in environment variables")
        return set()
    
    auth = HTTPBasicAuth(jira_email, jira_api_token)
    
    # JQL query to get issues with specific fix version
    jql = f"project = WOR AND fixversion = {fix_version} ORDER BY created DESC"
    
    url = "https://omnisinc.atlassian.net/rest/api/2/search"
    params = {
        'jql': jql,
        'fields': 'key',
        'maxResults': 999
    }
    
    try:
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        
        data = response.json()
        tickets = {issue['key'] for issue in data.get('issues', [])}
        return tickets
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching JIRA tickets: {e}")
        print(f"JIRA API Error: {e}", file=sys.stderr)
        sys.exit(1)

def get_jira_tickets_with_titles_from_api(fix_version: str) -> Dict[str, str]:
    """JIRA APIからfix versionに紐づくチケットとタイトルを取得
    Returns: {ticket_number: summary} の辞書
    """
    jira_email = os.environ.get('JIRA_EMAIL')
    jira_api_token = os.environ.get('JIRA_API_TOKEN')
    
    if not all([jira_email, jira_api_token]):
        print("Error: JIRA credentials not found in environment variables")
        return {}
    
    auth = HTTPBasicAuth(jira_email, jira_api_token)
    
    # JQL query to get issues with specific fix version
    jql = f"project = WOR AND fixversion = {fix_version} ORDER BY created DESC"
    
    url = "https://omnisinc.atlassian.net/rest/api/2/search"
    params = {
        'jql': jql,
        'fields': 'key,summary',  # summaryを追加
        'maxResults': 999
    }
    
    try:
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        
        data = response.json()
        ticket_titles = {}
        for issue in data.get('issues', []):
            key = issue['key']
            summary = issue.get('fields', {}).get('summary', '(タイトルなし)')
            ticket_titles[key] = summary
        
        return ticket_titles
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching JIRA tickets: {e}")
        print(f"JIRA API Error: {e}", file=sys.stderr)
        sys.exit(1)

def compare_tickets(release_tickets: Set[str], jira_tickets: Set[str]) -> Dict[str, Set[str]]:
    """リリースノートとJIRAのチケットを比較"""
    return {
        'only_in_release': release_tickets - jira_tickets,
        'only_in_jira': jira_tickets - release_tickets,
        'common': release_tickets & jira_tickets
    }


def main():
    parser = argparse.ArgumentParser(description='Verify JIRA tickets in release draft')
    parser.add_argument('--release-body-file', required=True, help='Path to file containing release body content')
    parser.add_argument('--release-name', required=True, help='Release name')
    parser.add_argument('--release-url', required=True, help='Release URL')
    
    args = parser.parse_args()
    
    # リリースボディをファイルから読み込む
    with open(args.release_body_file, 'r', encoding='utf-8') as f:
        release_body = f.read()
    
    # リリースノートからチケット番号を抽出
    release_tickets = extract_jira_tickets_from_release_notes(release_body)
    print(f"Found {len(release_tickets)} tickets in release notes: {sorted(release_tickets)}")
    
    # リリースノートからチケット番号とタイトルを抽出
    release_ticket_titles = extract_tickets_with_titles_from_release_notes(release_body)
    
    # Fix versionをJIRAリンクから抽出
    fix_version = extract_fix_version_from_jira_link(release_body)
    
    if not fix_version:
        print("Error: Could not find JIRA version link in release notes. Expected format: https://omnisinc.atlassian.net/projects/WOR/versions/{version_id}/...")
        sys.exit(1)
    
    print(f"Using fix version: {fix_version}")
    
    # JIRA APIからチケットを取得
    jira_tickets = get_jira_tickets_from_api(fix_version)
    print(f"Found {len(jira_tickets)} tickets in JIRA: {sorted(jira_tickets)}")
    
    # JIRA APIからチケットとタイトルを取得
    jira_ticket_titles = get_jira_tickets_with_titles_from_api(fix_version)
    
    # チケットを比較
    comparison = compare_tickets(release_tickets, jira_tickets)
    
    # 結果を出力
    print("\n=== Comparison Results ===")
    print(f"Only in GitHub Changed: {sorted(comparison['only_in_release'])}")
    print(f"Only in JIRA: {sorted(comparison['only_in_jira'])}")
    print(f"Common tickets: {len(comparison['common'])}")
    
    # GitHub Actions の出力として結果を設定（GITHUB_OUTPUT環境変数を使用）
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"only_in_release={','.join(sorted(comparison['only_in_release']))}\n")
            f.write(f"only_in_jira={','.join(sorted(comparison['only_in_jira']))}\n")
            f.write(f"common_count={len(comparison['common'])}\n")
            f.write(f"has_differences={'true' if comparison['only_in_release'] or comparison['only_in_jira'] else 'false'}\n")
            f.write(f"fix_version={fix_version}\n")
            
            
            
            # タイトル付きのリストを生成（差分チケットのみ）
            only_in_release_with_titles = '\\n'.join([
                f"• {ticket}: {release_ticket_titles.get(ticket, '(タイトルなし)')}" 
                for ticket in sorted(comparison['only_in_release'])
            ])
            only_in_jira_with_titles = '\\n'.join([
                f"• {ticket}: {jira_ticket_titles.get(ticket, '(タイトルなし)')}" 
                for ticket in sorted(comparison['only_in_jira'])
            ])
            
            f.write(f"only_in_release_with_titles={only_in_release_with_titles}\n")
            f.write(f"only_in_jira_with_titles={only_in_jira_with_titles}\n")
    
    # 不一致がある場合は終了コード1で終了
    if comparison['only_in_release'] or comparison['only_in_jira']:
        sys.exit(1)
    
    print("\n✅ All tickets match between release notes and JIRA!")

if __name__ == '__main__':
    main()