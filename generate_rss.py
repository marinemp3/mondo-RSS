#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSSフィード生成スクリプト - m12333.cn/qa から記事を抽出
Seleniumを使用して動的コンテンツを取得
GitHub Actionsで30分ごとに自動実行
"""

import os
import sys
import re
import hashlib
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# 設定
BASE_URL = "https://m12333.cn"
QA_URL = "https://m12333.cn/qa"
OUTPUT_FILE = "rss.xml"
# 日本のタイムゾーン（JST）
JST = timezone(timedelta(hours=9))

def setup_driver():
    """
    Chromeドライバーをセットアップ
    """
    options = Options()
    options.add_argument('--headless')  # ヘッドレスモード
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # ユーザーエージェントを設定
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"Chromeドライバーの起動に失敗: {e}")
        print("chromedriverがインストールされているか確認してください")
        sys.exit(1)

def fetch_articles_with_selenium():
    """
    Seleniumを使用してHTMLを取得し、記事を抽出
    """
    driver = None
    try:
        print("SeleniumでHTMLを取得中...")
        driver = setup_driver()
        
        # ページにアクセス
        print(f"  {QA_URL} にアクセス...")
        driver.get(QA_URL)
        
        # ページ読み込みを待機（最大30秒）
        wait = WebDriverWait(driver, 30)
        
        # 記事テーブルが表示されるまで待機
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "table-nopadding")))
            print("  記事テーブルを検出")
        except:
            print("  記事テーブルが見つからないため、全体の読み込みを待機")
            time.sleep(3)
        
        # ページソースを取得
        html = driver.page_source
        print(f"  HTML取得成功: {len(html)} 文字")
        
        # HTMLから記事を抽出
        articles = extract_articles_from_html(html)
        print(f"  記事を {len(articles)} 件抽出しました")
        
        return articles
        
    except Exception as e:
        print(f"Seleniumエラー: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    finally:
        if driver:
            driver.quit()
            print("  Chromeドライバーを終了")

def extract_articles_from_html(html_content):
    """
    HTMLコンテンツから記事を抽出する
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []
    
    # 方法1: テーブルから抽出
    table = soup.find('table', class_='table-nopadding')
    if not table:
        table = soup.find('table', {'class': lambda x: x and 'table-nopadding' in x})
    
    if not table:
        content_box = soup.find('div', class_='rightcontentbox')
        if content_box:
            table = content_box.find('table')
    
    if table:
        rows = table.find_all('tr')
        for row in rows:
            h3 = row.find('h3')
            if not h3:
                continue
            link = h3.find('a')
            if not link:
                continue
            
            title = link.get_text(strip=True)
            url = link.get('href', '')
            
            if not title or not url:
                continue
            
            # 絶対URLに変換
            if url.startswith('/'):
                url = urljoin(BASE_URL, url)
            elif not url.startswith('http'):
                url = urljoin(BASE_URL, '/' + url)
            
            # 日付情報を抽出
            date_cell = row.find('td', class_='text-muted')
            pub_date = None
            if date_cell:
                date_text = date_cell.get_text(strip=True)
                try:
                    pub_date = datetime.strptime(date_text, '%Y-%m-%d')
                    pub_date = pub_date.replace(tzinfo=JST)
                except ValueError:
                    pass
            
            if not pub_date:
                pub_date = datetime.now(JST)
            
            articles.append({
                'title': title,
                'link': url,
                'pubDate': pub_date,
                'guid': hashlib.md5(url.encode()).hexdigest(),
            })
    
    # テーブルから抽出できなかった場合のフォールバック
    if not articles:
        print("  テーブル抽出に失敗。正規表現で再試行...")
        articles = extract_articles_with_regex(html_content)
    
    return articles

def extract_articles_with_regex(html_content):
    """
    正規表現を使用してHTMLから記事を抽出（フォールバック用）
    """
    articles = []
    
    # 記事リンクを探すパターン
    pattern = r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html_content)
    
    # 日付パターン
    date_pattern = r'\[(\d{4}-\d{2}-\d{2})\]'
    dates = re.findall(date_pattern, html_content)
    
    # 抽出したリンクから記事を生成
    for i, (url, title) in enumerate(matches):
        if len(title) > 5 and ('/qa/' in url or '/qa?' in url or '/qa' in url):
            if url.startswith('/'):
                url = urljoin(BASE_URL, url)
            elif not url.startswith('http'):
                url = urljoin(BASE_URL, '/' + url)
            
            pub_date = None
            if i < len(dates):
                try:
                    pub_date = datetime.strptime(dates[i], '%Y-%m-%d')
                    pub_date = pub_date.replace(tzinfo=JST)
                except ValueError:
                    pass
            
            if not pub_date:
                pub_date = datetime.now(JST)
            
            articles.append({
                'title': title.strip(),
                'link': url,
                'pubDate': pub_date,
                'guid': hashlib.md5(url.encode()).hexdigest(),
            })
    
    # 重複を除去
    seen_urls = set()
    unique_articles = []
    for article in articles:
        if article['link'] not in seen_urls:
            seen_urls.add(article['link'])
            unique_articles.append(article)
    
    return unique_articles[:50]

def generate_rss(articles):
    """
    記事リストからRSSフィードを生成
    """
    if not articles:
        print("記事がありません。RSSを生成しません。")
        return False
    
    fg = FeedGenerator()
    fg.title("人事社保办事指南 - 问答指南")
    fg.link(href=QA_URL, rel="alternate")
    fg.link(href="https://raw.githubusercontent.com/yourusername/yourrepo/main/rss.xml", rel="self")
    fg.description("人力资源和社会保障/社会保险业务知识问答")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(JST))
    fg.generator("Python RSS Feed Generator (Selenium)")
    fg.author(name="人社通", email="")
    
    for article in articles[:50]:
        fe = fg.add_entry()
        fe.title(article['title'])
        fe.link(href=article['link'], rel="alternate")
        fe.guid(article['guid'], permalink=False)
        fe.pubDate(article['pubDate'])
        fe.description(f"{article['title']} - {article['link']}")
    
    rss_str = fg.rss_str(pretty=True)
    
    with open(OUTPUT_FILE, 'wb') as f:
        f.write(rss_str)
    
    print(f"RSSフィードを生成しました: {OUTPUT_FILE} (記事数: {len(articles)})")
    return True

def main():
    """
    メイン実行関数
    """
    print(f"=== RSSフィード生成開始: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')} ===")
    
    articles = fetch_articles_with_selenium()
    print(f"取得記事数: {len(articles)}")
    
    if articles:
        success = generate_rss(articles)
        if success:
            print("RSSフィード生成完了")
        else:
            print("RSSフィード生成失敗")
            sys.exit(1)
    else:
        print("記事が取得できませんでした")
        sys.exit(1)

if __name__ == "__main__":
    main()
