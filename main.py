import re
from datetime import datetime
import requests
import pandas as pd

# ----------------------------------------------------
# 1. 설정: 제공해주신 Apps Script 웹앱 URL
# ----------------------------------------------------
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbzYS4HlzoqQmkPSAlzzo6HaZlWastT7EqJFsyNBhEkG4V_ZYiK3rGVpRd7FFv4DnGlkBQ/exec"


def get_target_list():
    """Apps Script GET 요청으로 Target_List 읽어오기"""
    try:
        response = requests.get(GAS_WEBAPP_URL, allow_redirects=True, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[오류] Target_List를 불러오는 중 문제가 발생했습니다: {e}")
        return []


def send_to_sheets(rows):
    """Apps Script POST 요청으로 수집 데이터 Crawl_History 시트에 적재하기"""
    payload = {
        "sheetName": "Crawl_History",
        "rows": rows
    }
    try:
        # Apps Script 리다이렉트를 처리하기 위해 allow_redirects=True 필수
        response = requests.post(GAS_WEBAPP_URL, json=payload, allow_redirects=True, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[오류] 구글 시트로 데이터를 전송하는 중 문제가 발생했습니다: {e}")
        return None


def get_jinhak_html(url):
    """진학사 URL에 접근하여 한글 깨짐 없이 HTML 받아오기"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = 'utf-8'  # 한글 깨짐 방지
    return res.text


def parse_department_data(dfs, target_dept):
    """pandas로 파싱한 표 들 중 학과명(target_dept)을 찾아 데이터 추출"""
    for df in dfs:
        df_str = df.to_string()
        if target_dept in df_str:
            for _, row in df.iterrows():
                row_str_list = [str(val).strip() for val in row.values]

                # 해당 행에 target_dept 학과명이 있는지 확인
                if any(target_dept in cell for cell in row_str_list):
                    # 표의 오른쪽 끝 3개 컬럼: [모집인원, 지원자수, 경쟁률]
                    raw_reco = row_str_list[-3]
                    raw_apply = row_str_list[-2]
                    raw_ratio = row_str_list[-1]

                    # 정규식 정제 (숫자와 마침표만 추출)
                    reco_num = re.sub(r'[^0-9]', '', raw_reco)
                    apply_num = re.sub(r'[^0-9]', '', raw_apply)

                    ratio_match = re.search(r'([0-9.]+)', raw_ratio)
                    ratio = ratio_match.group(1) if ratio_match else raw_ratio

                    return reco_num, apply_num, ratio
    return None, None, None


def run_crawler():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"[{now_str}] 크롤링 및 수집 작업을 시작합니다...")

    # 1. 시트에서 Target_List 가져오기
    targets = get_target_list()
    if not targets:
        print("[알림] Target_List 시트에 설정된 데이터가 없거나 불러오지 못했습니다.")
        return

    print(f"총 {len(targets)}개의 타겟 학과를 확인했습니다.")

    # URL별로 그룹화 (중복 네트워크 요청 방지)
    url_map = {}
    for t in targets:
        url = t.get('URL')
        if url:
            if url not in url_map:
                url_map[url] = []
            url_map[url].append(t)

    new_history_rows = []

    # 2. 크롤링 수행
    for url, items in url_map.items():
        try:
            html_text = get_jinhak_html(url)
            dfs = pd.read_html(html_text)

            for item in items:
                target_id = item.get('Target_ID')
                dept_name = item.get('학과명')

                reco, apply, ratio = parse_department_data(dfs, dept_name)

                if apply is not None and apply != "":
                    print(f"  └─ [{dept_name}] 수집 성공 | 모집: {reco}명 | 지원: {apply}명 | 경쟁률: {ratio}:1")
                    # Crawl_History 행 양식: [수집시각, Target_ID, 모집인원, 지원인원, 경쟁률]
                    new_history_rows.append([now_str, target_id, reco, apply, ratio])
                else:
                    print(f"  └─ [{dept_name}] 데이터 추출 실패 (학과명을 표에서 찾을 수 없음)")

        except Exception as e:
            print(f"[오류] URL 크롤링 중 에러 발생 ({url}): {e}")

    # 3. Apps Script를 통해 구글 시트 Crawl_History에 적재
    if new_history_rows:
        result = send_to_sheets(new_history_rows)
        print(f"\n[구글 시트 전송 결과] {result}")
    else:
        print("\n[알림] 저장할 새로운 데이터가 없습니다.")


if __name__ == '__main__':
    run_crawler()