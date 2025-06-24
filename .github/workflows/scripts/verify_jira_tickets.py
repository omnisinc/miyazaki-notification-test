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

def extract_fix_version_from_release_name(release_name: str) -> str:
    """リリース名からfix versionを抽出（例: v3.13.8-0 -> 11399）"""
    # この部分は実際のJIRAのversion IDマッピングに応じて調整が必要
    # 仮実装として、環境変数でマッピングを管理
    version_mapping = json.loads(os.environ.get('JIRA_VERSION_MAPPING', '{}'))
    
    # リリース名からバージョン番号を抽出
    version_match = re.search(r'v?(\d+\.\d+\.\d+)', release_name)
    if version_match:
        version = version_match.group(1)
        return version_mapping.get(version, '')
    return ''

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
    jira_base_url = os.environ.get('JIRA_BASE_URL', 'https://omnisinc.atlassian.net')
    jira_email = os.environ.get('JIRA_EMAIL')
    jira_api_token = os.environ.get('JIRA_API_TOKEN')
    
    if not all([jira_email, jira_api_token]):
        print("Error: JIRA credentials not found in environment variables")
        return set()
    
    auth = HTTPBasicAuth(jira_email, jira_api_token)
    
    # JQL query to get issues with specific fix version
    jql = f"project = WOR AND fixversion = {fix_version} ORDER BY created DESC"
    
    url = f"{jira_base_url}/rest/api/2/search"
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
        return set()

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
    parser.add_argument('--fix-version', help='JIRA fix version (optional, will try to extract from release name)')
    
    args = parser.parse_args()
    
    # リリースボディをファイルから読み込む
    with open(args.release_body_file, 'r', encoding='utf-8') as f:
        release_body = f.read()
    
    # リリースノートからチケット番号を抽出
    release_tickets = extract_jira_tickets_from_release_notes(release_body)
    print(f"Found {len(release_tickets)} tickets in release notes: {sorted(release_tickets)}")
    
    # Fix versionをJIRAリンクから抽出
    fix_version = extract_fix_version_from_jira_link(release_body)
    
    if not fix_version:
        print("Error: Could not find JIRA version link in release notes. Expected format: https://omnisinc.atlassian.net/projects/WOR/versions/{version_id}/...")
        sys.exit(1)
    
    print(f"Using fix version: {fix_version}")
    
    # JIRA APIからチケットを取得
    jira_tickets = get_jira_tickets_from_api(fix_version)
    print(f"Found {len(jira_tickets)} tickets in JIRA: {sorted(jira_tickets)}")
    
    # チケットを比較
    comparison = compare_tickets(release_tickets, jira_tickets)
    
    # 結果を出力
    print("\n=== Comparison Results ===")
    print(f"Only in release notes: {sorted(comparison['only_in_release'])}")
    print(f"Only in JIRA: {sorted(comparison['only_in_jira'])}")
    print(f"Common tickets: {len(comparison['common'])}")
    
    # GitHub Actions の出力として結果を設定（GITHUB_OUTPUT環境変数を使用）
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"only_in_release={','.join(sorted(comparison['only_in_release']))}\n")
            f.write(f"only_in_jira={','.join(sorted(comparison['only_in_jira']))}\n")
            f.write(f"common_count={len(comparison['common'])}\n")
            f.write(f"has_differences={'true' if comparison['only_in_release'] or comparison['only_in_jira'] else 'false'}\n")
            
            # Slack表示用の改行区切りリストも出力
            only_in_release_list = '\\n'.join([f"• {ticket}" for ticket in sorted(comparison['only_in_release'])])
            only_in_jira_list = '\\n'.join([f"• {ticket}" for ticket in sorted(comparison['only_in_jira'])])
            f.write(f"only_in_release_list={only_in_release_list}\n")
            f.write(f"only_in_jira_list={only_in_jira_list}\n")
    
    # 不一致がある場合は終了コード1で終了
    if comparison['only_in_release'] or comparison['only_in_jira']:
        sys.exit(1)
    
    print("\n✅ All tickets match between release notes and JIRA!")

if __name__ == '__main__':
    main()