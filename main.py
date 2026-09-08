import re
from datetime import datetime
import io
import requests
import pandas as pd
from bs4 import BeautifulSoup

GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbzYS4HlzoqQmkPSAlzzo6HaZlWastT7EqJFsyNBhEkG4V_ZYiK3rGVpRd7FFv4DnGlkBQ/exec"


def get_target_list():
    try:
        response = requests.get(GAS_WEBAPP_URL, allow_redirects=True, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[오류] Target_List를 불러오는 중 문제가 발생했습니다: {e}")
        return []


def send_to_sheets(rows):
    payload = {"sheetName": "Crawl_History", "rows": rows}
    try:
        response = requests.post(GAS_WEBAPP_URL, json=payload, allow_redirects=True, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[오류] 구글 시트로 데이터를 전송하는 중 문제가 발생했습니다: {e}")
        return None


def get_jinhak_dfs(url):
    """진학사 URL에서 테이블을 직접 추출하는 함수"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.jinhakapply.com/"
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = 'euc-kr'  # 진학사 기본 인코딩

    if res.status_code != 200:
        raise ValueError(f"HTTP 상태 코드 에러: {res.status_code}")

    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table')

    if not tables:
        raise ValueError("페이지에서 <table> 태그를 찾지 못했습니다. (보안 차단 가능성)")

    # BeautifulSoup으로 추출한 table들을 DataFrame 목록으로 변환
    dfs = pd.read_html(io.StringIO(str(tables)))
    return dfs


def parse_department_data(dfs, target_dept):
    for df in dfs:
        df_str = df.to_string()
        if target_dept in df_str:
            for _, row in df.iterrows():
                row_str_list = [str(val).strip() for val in row.values]

                if any(target_dept in cell for cell in row_str_list):
                    raw_reco = row_str_list[-3]
                    raw_apply = row_str_list[-2]
                    raw_ratio = row_str_list[-1]

                    reco_num = re.sub(r'[^0-9]', '', raw_reco)
                    apply_num = re.sub(r'[^0-9]', '', raw_apply)

                    ratio_match = re.search(r'([0-9.]+)', raw_ratio)
                    ratio = ratio_match.group(1) if ratio_match else raw_ratio

                    return reco_num, apply_num, ratio
    return None, None, None


def run_crawler():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"[{now_str}] 크롤링 및 수집 작업을 시작합니다...")

    targets = get_target_list()
    if not targets:
        print("[알림] Target_List 시트에 설정된 데이터가 없거나 불러오지 못했습니다.")
        return

    print(f"총 {len(targets)}개의 타겟 학과를 확인했습니다.")

    url_map = {}
    for t in targets:
        url = t.get('URL')
        if url:
            if url not in url_map:
                url_map[url] = []
            url_map[url].append(t)

    new_history_rows = []

    for url, items in url_map.items():
        try:
            dfs = get_jinhak_dfs(url)

            for item in items:
                target_id = item.get('Target_ID')
                dept_name = item.get('학과명')

                reco, apply, ratio = parse_department_data(dfs, dept_name)

                if apply is not None and apply != "":
                    print(f"  └─ [{dept_name}] 수집 성공 | 모집: {reco}명 | 지원: {apply}명 | 경쟁률: {ratio}:1")
                    new_history_rows.append([now_str, target_id, reco, apply, ratio])
                else:
                    print(f"  └─ [{dept_name}] 데이터 추출 실패 (학과명을 표에서 찾을 수 없음)")

        except Exception as e:
            print(f"[오류] URL 크롤링 중 에러 발생 ({url}): {e}")

    if new_history_rows:
        result = send_to_sheets(new_history_rows)
        print(f"\n[구글 시트 전송 결과] {result}")
    else:
        print("\n[알림] 저장할 새로운 데이터가 없습니다.")


if __name__ == '__main__':
    run_crawler()