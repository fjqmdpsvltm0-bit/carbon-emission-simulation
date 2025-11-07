# 🚚 친환경 물류 경로 시뮬레이션 (최종 수정)
# ✅ 수소: get_hydrogen_co2_per_km() = 생산CO2 (운영 = 0)
# ✅ 내연기관: 운영CO2 + 생산CO2 (각 차종별 고정값)
# ✅ Anaconda Prompt 완전 반영

import streamlit as st
import requests
from datetime import datetime, timedelta
import folium
from streamlit_folium import st_folium
import math

st.set_page_config(layout="wide", page_title="물류 경로 분석")

CLIENT_ID           = st.secrets[CLIENT_ID]
CLIENT_SECRET       = st.secrets[CLIENT_SECRET]
SEARCH_CLIENT_ID    = st.secrets[SEARCH_CLIENT_ID]
SEARCH_CLIENT_SECRET= st.secrets[SEARCH_CLIENT_SECRET]

# ============================================================================
# 【탄소배출 상수】
# ============================================================================

# ✅ 내연기관: 생산 CO2 배출계수 (kg/km)
MANUFACTURING_CO2_COEFFICIENT = {
    "소형": 0.050,      # kg/km
    "중형": 0.070,      # kg/km
    "대형": 0.0667      # kg/km
}

def get_hydrogen_co2_per_km(load_percent):
    """
    수소트럭 생산 CO2 배출량 (kg/km) - 적재율 함수
    
    공식: CO2/km = 0.089 × load_percent + 0.192
    (운영과정은 0, 생산과정만 카운트)
    
    범위:
    - 0% 적재: 0.192 kg/km
    - 50% 적재: 0.2335 kg/km
    - 100% 적재: 0.281 kg/km
    """
    co2_per_km = 0.089 * load_percent + 0.192
    return co2_per_km

def get_hydrogen_h2_consumption(load_percent):
    """
    수소 소비량 계산 (kg/100km, 적재율 함수)
    공식: H2 = 7.75 + 1.75 × load_percent
    """
    h2_consumption = (7.75 + 1.75 * load_percent)
    return h2_consumption

def get_hydrogen_speed_factor(load_percent):
    """
    수소트럭 속도계수 계산 (에너지 역수 관계)
    공식: Speed_factor = 7.75 / H2_consumption
    """
    h2_consumption = get_hydrogen_h2_consumption(load_percent)
    hydrogen_speed_factor = 7.75 / h2_consumption
    return hydrogen_speed_factor

# ============================================================================
# TABLE2: 경사도별, 적재율별 연료소비량 데이터 (L/km)
# ============================================================================

TABLE2_DATA = {
    "소형": {
        0: {0.25: 0.32, 0.50: 0.32, 1.00: 0.32},
        1: {0.25: 0.33, 0.50: 0.33, 1.00: 0.33},
        2: {0.25: 0.37, 0.50: 0.34, 1.00: 0.34},
        3: {0.25: 0.34, 0.50: 0.34, 1.00: 0.35},
        4: {0.25: 0.35, 0.50: 0.35, 1.00: 0.36},
        5: {0.25: 0.36, 0.50: 0.36, 1.00: 0.37},
        6: {0.25: 0.36, 0.50: 0.37, 1.00: 0.38}
    },
    "중형": {
        0: {0.25: 0.33, 0.50: 0.34, 1.00: 0.34},
        1: {0.25: 0.36, 0.50: 0.36, 1.00: 0.38},
        2: {0.25: 0.38, 0.50: 0.39, 1.00: 0.41},
        3: {0.25: 0.40, 0.50: 0.41, 1.00: 0.44},
        4: {0.25: 0.42, 0.50: 0.44, 1.00: 0.47},
        5: {0.25: 0.44, 0.50: 0.46, 1.00: 0.48},
        6: {0.25: 0.46, 0.50: 0.48, 1.00: 0.49}
    },
    "대형": {
        0: {0.25: 0.37, 0.50: 0.38, 1.00: 0.41},
        1: {0.25: 0.44, 0.50: 0.47, 1.00: 0.54},
        2: {0.25: 0.51, 0.50: 0.56, 1.00: 0.61},
        3: {0.25: 0.58, 0.50: 0.62, 1.00: 0.67},
        4: {0.25: 0.62, 0.50: 0.66, 1.00: 0.74},
        5: {0.25: 0.65, 0.50: 0.71, 1.00: 0.83},
        6: {0.25: 0.70, 0.50: 0.78, 1.00: 0.99}
    }
}

REFERENCE_FUEL = {
    "소형": 0.32,
    "중형": 0.33,
    "대형": 0.37
}

vehicle_reference_specs = {
    "소형": {"engine_kw": 97.8, "empty_weight": 1750, "max_load": 1000},
    "중형": {"engine_kw": 205.9, "empty_weight": 5200, "max_load": 5000},
    "대형": {"engine_kw": 397.1, "empty_weight": 15000, "max_load": 25000},
    "수소-대형": {
        "fuel_cell_kw": 180,
        "motor_kw": 350,
        "engine_kw": 350,
        "empty_weight": 19500,
        "max_load": 17500,
        "tank_capacity": 31,
        "description": "현대 XCIENT Fuel Cell (180kW×2 스택, 350kW 모터)"
    }
}

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    .stButton button { border-radius: 8px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 【기본 함수들】
# ============================================================================

def haversine_distance(lat1, lng1, lat2, lng2):
    """두 지점 간 거리 계산 (km)"""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def split_polyline_by_1km_distance(polyline_coords):
    """Polyline을 정확히 1km씩 분할"""
    if not polyline_coords or len(polyline_coords) < 2:
        return []
    
    segments = []
    current_segment = []
    cumulative_distance = 0.0
    segment_num = 1
    
    for idx, coord in enumerate(polyline_coords):
        current_segment.append(coord)
        
        if idx > 0:
            prev_coord = polyline_coords[idx - 1]
            lat1, lng1 = prev_coord[1], prev_coord[0]
            lat2, lng2 = coord[1], coord[0]
            
            distance = haversine_distance(lat1, lng1, lat2, lng2)
            cumulative_distance += distance
            
            if cumulative_distance >= 1.0:
                segments.append({
                    'segment_num': segment_num,
                    'path': current_segment.copy(),
                    'distance_km': cumulative_distance,
                    'start_coord': current_segment[0],
                    'end_coord': current_segment[-1]
                })
                
                segment_num += 1
                current_segment = [coord]
                cumulative_distance = 0.0
    
    if current_segment and cumulative_distance > 0:
        segments.append({
            'segment_num': segment_num,
            'path': current_segment,
            'distance_km': cumulative_distance,
            'start_coord': current_segment[0],
            'end_coord': current_segment[-1]
        })
    
    return segments

def match_guide_data_to_segments(guide_array, segments, grade=0):
    """Guide 데이터를 Segment에 매칭"""
    
    if not guide_array:
        return segments
    
    cumulative_distance = 0
    speed_segments = []
    
    for guide in guide_array:
        g_dist_km = guide.get('distance', 0) / 1000
        g_dur_hour = guide.get('duration', 0) / 3600000
        
        if g_dur_hour > 0:
            g_speed = g_dist_km / g_dur_hour
        else:
            g_speed = 60
        
        speed_segments.append({
            'start': cumulative_distance,
            'end': cumulative_distance + g_dist_km,
            'speed': g_speed
        })
        
        cumulative_distance += g_dist_km
    
    segment_cumulative_dist = 0
    
    for segment in segments:
        seg_distance_km = segment['distance_km']
        seg_start = segment_cumulative_dist
        seg_end = segment_cumulative_dist + seg_distance_km
        
        total_weighted_speed = 0
        total_overlap = 0
        
        for speed_seg in speed_segments:
            overlap_start = max(seg_start, speed_seg['start'])
            overlap_end = min(seg_end, speed_seg['end'])
            overlap_dist = max(0, overlap_end - overlap_start)
            
            if overlap_dist > 0:
                total_weighted_speed += overlap_dist * speed_seg['speed']
                total_overlap += overlap_dist
        
        if total_overlap > 0:
            avg_speed = total_weighted_speed / total_overlap
        else:
            avg_speed = 60
        
        if avg_speed > 0:
            seg_duration_ms = (seg_distance_km / avg_speed) * 3600000
        else:
            seg_duration_ms = 0
        
        congestion_ratio, congestion_level = calculate_congestion_from_speed(avg_speed)
        
        segment['avg_speed'] = avg_speed
        segment['congestion_ratio'] = congestion_ratio
        segment['congestion_level'] = congestion_level
        segment['color'] = congestion_to_color(congestion_ratio)
        segment['label'] = congestion_to_label(congestion_ratio)
        segment['guide_duration_ms'] = seg_duration_ms
        segment['grade'] = grade
        segment_cumulative_dist += seg_distance_km
    
    return segments

def calculate_congestion_from_speed(final_speed):
    """평균 속도로부터 혼잡도 계산 (0~100%)"""
    ideal_speed = 80
    
    if final_speed >= ideal_speed:
        congestion_ratio = 0
    elif final_speed >= 60:
        congestion_ratio = ((ideal_speed - final_speed) / ideal_speed) * 30
    elif final_speed >= 40:
        congestion_ratio = 30 + ((60 - final_speed) / 20) * 30
    elif final_speed >= 20:
        congestion_ratio = 60 + ((40 - final_speed) / 20) * 20
    else:
        congestion_ratio = 80 + min(20, (20 - final_speed))
    
    congestion_level = 1 if congestion_ratio < 20 else (2 if congestion_ratio < 40 else (3 if congestion_ratio < 60 else (4 if congestion_ratio < 80 else 5)))
    
    return min(100, max(0, congestion_ratio)), congestion_level

def congestion_to_color(congestion_ratio):
    """혼잡도 비율(%)을 색상으로 변환"""
    if congestion_ratio < 20:
        return '#00AA00'
    elif congestion_ratio < 40:
        return '#FFFF00'
    elif congestion_ratio < 60:
        return '#FFA500'
    elif congestion_ratio < 80:
        return '#FF0000'
    else:
        return '#808080'

def congestion_to_label(congestion_ratio):
    """혼잡도를 텍스트로 변환"""
    if congestion_ratio < 20:
        return "원활 🟢"
    elif congestion_ratio < 40:
        return "약간혼잡 🟡"
    elif congestion_ratio < 60:
        return "보통 🟠"
    elif congestion_ratio < 80:
        return "심함 🔴"
    else:
        return "극심 🔴"

def get_elevation_from_api(lat, lng, debug=True):
    """고도 정보 받기 (디버그 개선)"""
    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lng}"
    try:
        response = requests.get(url, timeout=10)  # timeout을 10초로 단축
        response.raise_for_status()  # HTTP 오류 명시적 확인
        
        data = response.json()
        
        if not data.get("results"):
            if debug:
                print(f"⚠️  No results in API response for ({lat:.4f}, {lng:.4f})")
            return None  # 0 대신 None 반환
        
        elevation = data["results"][0]["elevation"]
        if debug:
            print(f"✓ Elevation found: ({lat:.4f}, {lng:.4f}) = {elevation}m")
        return elevation
        
    except requests.exceptions.Timeout:
        if debug:
            print(f"✗ Timeout: Open Elevation API ({lat:.4f}, {lng:.4f})")
    except requests.exceptions.ConnectionError:
        if debug:
            print(f"✗ Connection Error: ({lat:.4f}, {lng:.4f})")
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"✗ Request Error: {str(e)}")
    except ValueError as e:
        if debug:
            print(f"✗ JSON Decode Error: {str(e)}")
    except Exception as e:
        if debug:
            print(f"✗ Unexpected Error: {str(e)}")
    
    return None  # ← None을 반환


def calculate_grade(start_lat, start_lng, end_lat, end_lng, distance_km):
    """경사도 계산"""
    start_elev = get_elevation_from_api(start_lat, start_lng, debug=True)
    end_elev = get_elevation_from_api(end_lat, end_lng, debug=True)
    
    # None인 경우 (API 실패)
    if start_elev is None or end_elev is None:
        print(f"⚠️  Grade calculation failed: start={start_elev}, end={end_elev}")
        return 0
    
    elevation_diff = end_elev - start_elev
    distance_m = distance_km * 1000
    
    if distance_m > 0:
        grade_percent = (elevation_diff / distance_m) * 100
    else:
        grade_percent = 0
    
    grade_result = min(max(grade_percent, -6), 6)
    print(f"✓ Grade calculated: {grade_percent:.2f}% → {grade_result:.1f}% (capped)")
    return grade_result

# ============================================================================
# 【탄소배출 계수 계산 - 핵심】
# ============================================================================

def calculate_operation_co2_coefficient(vehicle_type, final_speed):
    """
    운영 CO2 배출계수 계산 (kg/km)
    
    【수소】: 0 (운영과정 배출 없음)
    【내연기관】: 속도 기반
    """
    
    if vehicle_type == "수소-대형":
        # 🔋 수소: 운영 배출 = 0
        return 0.0
    
    # ⛽ 내연기관: 속도 기반 운영 CO2
    if vehicle_type == "소형":
        operation_co2 = 1250.4831 * (final_speed ** -0.4630) if final_speed < 65.4 else 0.0292 * (final_speed ** 2) - 2.9530 * final_speed + 258.3205
    elif vehicle_type == "중형":
        operation_co2 = 1385.8860 * (final_speed ** -0.4184) if final_speed < 65.4 else 1.6720 * final_speed + 141.2224
    elif vehicle_type == "대형":
        operation_co2 = 3351.2892 * (final_speed ** -0.4407)
    else:
        operation_co2 = 0
    
    operation_co2 = max(operation_co2 / 1000, 0)  # g/km → kg/km
    
    return operation_co2

def calculate_manufacturing_co2_coefficient(vehicle_type, load_percent):
    """
    생산 CO2 배출계수 계산 (kg/km)
    
    【수소】: get_hydrogen_co2_per_km(load_percent)
    【내연기관】: MANUFACTURING_CO2_COEFFICIENT 고정값
    """
    
    if vehicle_type == "수소-대형":
        # 🔋 수소: 생산 CO2 = get_hydrogen_co2_per_km()
        return get_hydrogen_co2_per_km(load_percent)
    
    # ⛽ 내연기관: 고정값
    return MANUFACTURING_CO2_COEFFICIENT.get(vehicle_type, 0)

# ============================================================================
# 【속도계수 계산】
# ============================================================================

def calculate_speed_factor_from_table2(vehicle_type, load_percent, grade):
    """TABLE2 기반 속도 계수 계산"""
    
    if vehicle_type == "수소-대형":
        hydrogen_speed_factor = get_hydrogen_speed_factor(load_percent)
        return hydrogen_speed_factor
    
    fuel_actual = get_table2_fuel_consumption(vehicle_type, load_percent, grade)
    fuel_reference = REFERENCE_FUEL.get(vehicle_type, 0.35)
    
    if fuel_actual > 0:
        speed_factor = math.sqrt(fuel_reference / fuel_actual)
    else:
        speed_factor = 1.0
    
    speed_factor = max(0.50, min(1.50, speed_factor))
    
    return speed_factor

def get_table2_fuel_consumption(vehicle_type, load_percent, grade):
    """TABLE2에서 연료소비량 조회"""
    
    if vehicle_type == "수소-대형":
        h2_consumption = get_hydrogen_h2_consumption(load_percent)
        return h2_consumption / 100
    
    if grade < 0:
        effective_grade = 0
    else:
        effective_grade = min(grade, 6)
    
    if load_percent <= 0.25:
        load_lower = 0.25
        load_upper = 0.25
        load_weight = 0.0
    elif load_percent >= 1.00:
        load_lower = 1.00
        load_upper = 1.00
        load_weight = 0.0
    elif load_percent <= 0.50:
        load_lower = 0.25
        load_upper = 0.50
        load_weight = (load_percent - 0.25) / (0.50 - 0.25)
    else:
        load_lower = 0.50
        load_upper = 1.00
        load_weight = (load_percent - 0.50) / (1.00 - 0.50)
    
    grade_lower = int(effective_grade)
    grade_upper = min(grade_lower + 1, 6)
    grade_weight = effective_grade - grade_lower
    
    try:
        fuel_ll = TABLE2_DATA[vehicle_type][grade_lower][load_lower]
        fuel_lu = TABLE2_DATA[vehicle_type][grade_lower][load_upper]
        fuel_ul = TABLE2_DATA[vehicle_type][grade_upper][load_lower]
        fuel_uu = TABLE2_DATA[vehicle_type][grade_upper][load_upper]
    except KeyError:
        return REFERENCE_FUEL.get(vehicle_type, 0.35)
    
    fuel_lower = fuel_ll + (fuel_ul - fuel_ll) * grade_weight
    fuel_upper = fuel_lu + (fuel_uu - fuel_lu) * grade_weight
    fuel_interpolated = fuel_lower + (fuel_upper - fuel_lower) * load_weight
    
    return fuel_interpolated

def calculate_vehicle_speeds(naver_api_speed, speed_factor, grade_percent, vehicle_type):
    """최종 속도 계산"""
    final_speed = naver_api_speed * speed_factor
    
    return {
        "네이버_기본속도": round(naver_api_speed, 1),
        "테이블2_속도계수": round(speed_factor, 3),
        "예상_평균속도": round(final_speed, 1)
    }

def search_local(q):
    """지역 검색"""
    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {"X-Naver-Client-Id": SEARCH_CLIENT_ID, "X-Naver-Client-Secret": SEARCH_CLIENT_SECRET}
    try:
        return requests.get(url, headers=headers, params={"query": q, "display": 10}, timeout=50).json().get("items", [])
    except:
        return []

def geocode_address(address):
    """주소 좌표 변환"""
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {"X-NCP-APIGW-API-KEY-ID": CLIENT_ID, "X-NCP-APIGW-API-KEY": CLIENT_SECRET}
    try:
        res = requests.get(url, headers=headers, params={"query": address}, timeout=50)
        data = res.json()
        if data.get("addresses") and len(data["addresses"]) > 0:
            addr = data["addresses"][0]
            return [{
                "title": addr.get("roadAddress") or addr.get("jibunAddress") or address,
                "address": addr.get("roadAddress") or addr.get("jibunAddress") or address,
                "mapx": str(int(float(addr["x"]) * 1e7)),
                "mapy": str(int(float(addr["y"]) * 1e7)),
                "category": "주소",
                "telephone": ""
            }]
        return []
    except:
        return []

def search_local_or_geocode(query):
    """지역 검색 또는 좌표 변환"""
    items = search_local(query)
    return items if items else geocode_address(query)

def get_user_location():
    """사용자 위치 조회"""
    url = "https://geolocation.apigw.ntruss.com/geolocation/v2/geoLocation"
    headers = {"X-NCP-APIGW-API-KEY-ID": CLIENT_ID, "X-NCP-APIGW-API-KEY": CLIENT_SECRET}
    try:
        res = requests.get(url, headers=headers, timeout=50)
        data = res.json()
        if "location" in data:
            return data["location"]["lat"], data["location"]["lng"]
    except:
        pass
    return 37.566, 126.978

def get_all_route_types_with_guide_matching(locations, vehicle_type, current_load):
    """3가지 경로 조회 + Guide 데이터 매칭"""
    vehicle_cartype = {"소형": 1, "중형": 2, "대형": 3, "수소-대형": 5}
    
    specs = vehicle_reference_specs.get(vehicle_type, {})
    max_load = specs.get("max_load", 1)
    load_percent = (current_load / max_load) if max_load > 0 else 0
    load_percent = min(1.0, max(0.25, load_percent))
    
    all_routes = {'traoptimal': [], 'trafast': [], 'tracomfort': []}
    
    url = "https://maps.apigw.ntruss.com/map-direction/v1/driving"
    headers = {"X-NCP-APIGW-API-KEY-ID": CLIENT_ID, "X-NCP-APIGW-API-KEY": CLIENT_SECRET}
    
    for route_type in ['traoptimal', 'trafast', 'tracomfort']:
        st.info(f"🚗 {route_type} 경로 조회 중...")
        
        for i in range(len(locations) - 1):
            start_lat, start_lng, start_info = locations[i]
            end_lat, end_lng, end_info = locations[i + 1]
            
            params = {
                "start": f"{start_lng},{start_lat}",
                "goal": f"{end_lng},{end_lat}",
                "cartype": vehicle_cartype.get(vehicle_type, 3),
                "option": route_type
            }
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                route_data = response.json()
                
                if "route" not in route_data or route_type not in route_data["route"]:
                    continue
                
                route = route_data["route"][route_type][0]
                summary = route["summary"]
                path = route["path"]
                guide = route.get("guide", [])
                
                segments = split_polyline_by_1km_distance(path)
                grade_value = calculate_grade(
                    start_lat, start_lng, 
                    end_lat, end_lng, 
                    summary['distance'] / 1000
                    )
                segments = match_guide_data_to_segments(guide, segments, grade_value)
                
                segment = {
                    "segment_num": i + 1,
                    "start_info": start_info,
                    "end_info": end_info,
                    "start_coords": (start_lat, start_lng),
                    "end_coords": (end_lat, end_lng),
                    "distance_km": summary["distance"] / 1000,
                    "duration_min": summary["duration"] / 60000,
                    "path": path,
                    "segments": segments,
                    "route_type_used": route_type,
                    "load_percent": load_percent
                }
                all_routes[route_type].append(segment)
            
            except Exception as e:
                st.error(f"❌ 구간 {i+1} {route_type} 오류: {str(e)}")
    
    return all_routes

# ============================================================================
# 【Anaconda Prompt 출력 함수】
# ============================================================================

def print_segment_details_to_console(route_result_data, route_type, vehicle_type, load_percent, grade):
    """
    ✅ 수정: 운영 + 생산 분리 표시
    
    【수소】: 운영=0, 생산=get_hydrogen_co2_per_km()
    【내연기관】: 운영=속도기반, 생산=고정값
    """
    
    segments_data = route_result_data.get('segments', [])
    
    all_subsegments = []
    total_distance = 0
    total_duration_ms = 0
    congestion_list = []
    total_co2 = 0  # ✅ 자동 합산
    
    subseg_counter = 1
    
    for seg_idx, seg in enumerate(segments_data):
        segment_list = seg.get('segments', [])
        
        for subseg_idx, subseg in enumerate(segment_list):
            distance_km = subseg.get('distance_km', 0)
            naver_avg_speed = subseg.get('avg_speed', 0)
            congestion_ratio = subseg.get('congestion_ratio', 0)
            congestion_label = subseg.get('label', '미분류')
            guide_duration_ms = subseg.get('guide_duration_ms', 0)
            
            segment_grade = subseg.get('grade', grade)
            
            # 속도계수
            speed_factor = calculate_speed_factor_from_table2(
                vehicle_type,
                load_percent,
                segment_grade
            )
            
            final_speed = naver_avg_speed * speed_factor
            
            # 【연료/H2】
            fuel_or_h2 = get_table2_fuel_consumption(vehicle_type, load_percent, segment_grade)
            
            # ✅ 핵심: 운영 + 생산 분리 계산
            operation_co2_coef = calculate_operation_co2_coefficient(vehicle_type, final_speed)
            manufacturing_co2_coef = calculate_manufacturing_co2_coefficient(vehicle_type, load_percent)
            total_co2_coef = operation_co2_coef + manufacturing_co2_coef
            
            # ✅ 구간 CO2 = (운영 + 생산) × 거리
            segment_co2 = total_co2_coef * distance_km
            
            # 【H2 소비】
            if vehicle_type == "수소-대형":
                h2_total = fuel_or_h2 * distance_km
            else:
                h2_total = 0
            
            all_subsegments.append({
                'section': subseg_counter,
                'distance_km': distance_km,
                'naver_speed': naver_avg_speed,
                'fuel_or_h2': fuel_or_h2,
                'speed_factor': speed_factor,
                'final_speed': final_speed,
                'operation_coef': operation_co2_coef,
                'manufacturing_coef': manufacturing_co2_coef,
                'total_coef': total_co2_coef,
                'segment_co2': segment_co2,
                'segment_grade': segment_grade,
                'congestion_ratio': congestion_ratio,
                'congestion_label': congestion_label,
                'duration_ms': guide_duration_ms,
                'h2_total': h2_total
            })
            
            total_distance += distance_km
            total_duration_ms += guide_duration_ms
            congestion_list.append(congestion_ratio)
            total_co2 += segment_co2  # ✅ 자동 합산
            
            subseg_counter += 1
    
    # 【콘솔 헤더】
    print(f"🚗 경로 타입: {route_type.upper()} | 차종: {vehicle_type} | 적재율: {load_percent*100:.1f}%")
    
    if vehicle_type == "수소-대형":
        print("🔋 [수소] 운영=0, 생산=get_hydrogen_co2_per_km() (생산과정만 카운트)")
        print(f"{'Sec':<5} {'Dist':<8} {'Naver':<10} {'Fuel':<12} {'Op':<10} {'Mfg':<10} {'Total':<10} {'Grade':<7} {'Final':<10} {'Cong%':<8} {'CO2':<10} {'Label':<18}")
        print(f"{'':5} {'(km)':<8} {'(km/h)':<10} {'(kg/100km)':<12} {'(kg/km)':<10} {'(kg/km)':<10} {'(kg/km)':<10} {'(%)':<7} {'(km/h)':<10} {'':8} {'(kg)':<10}")
    else:
        print("⛽ [내연기관] 운영=속도기반, 생산=고정값 (운영 + 생산 = 최종)")
        print(f"{'Sec':<5} {'Dist':<8} {'Naver':<10} {'Fuel':<10} {'Op':<10} {'Mfg':<10} {'Total':<10} {'Grade':<7} {'Final':<10} {'Cong%':<8} {'CO2':<10} {'Label':<18}")
        print(f"{'':5} {'(km)':<8} {'(km/h)':<10} {'(L/km)':<10} {'(kg/km)':<10} {'(kg/km)':<10} {'(kg/km)':<10} {'(%)':<7} {'(km/h)':<10} {'':8} {'(kg)':<10}")
    
    print("\n【 DEBUG: Grade 적용 확인 】")
    for seg_idx, seg in enumerate(segments_data[:2]):  # 처음 2개만
        print(f"\nSegment {seg_idx}:")
    print(f"  seg['grade'] = {seg.get('grade', 'MISSING')}")
    
    segment_list = seg.get('segments', [])
    print(f"  segment_list 길이 = {len(segment_list)}")
    
    if segment_list:
        for sub_idx, subseg in enumerate(segment_list[:3]):
            seg_grade = subseg.get('grade', 'MISSING')
            print(f"    subseg {sub_idx}: grade = {seg_grade}")
    else:
        print("  ← ⚠️  segment_list가 비어있음! (기본값만 사용)")
    # ✅ 데이터 출력
    for subseg in all_subsegments:
        print(f"{subseg['section']:<5} {subseg['distance_km']:<8.2f} {subseg['naver_speed']:<10.1f} "
              f"{subseg['fuel_or_h2']:<12.4f} {subseg['operation_coef']:<10.4f} "
              f"{subseg['manufacturing_coef']:<10.4f} {subseg['total_coef']:<10.4f} "
              f"{subseg['segment_grade']:<7.1f} {subseg['final_speed']:<10.1f} {subseg['congestion_ratio']:<8.1f} "
              f"{subseg['segment_co2']:<10.3f} {subseg['congestion_label']:<18}")
    
    
    # 【요약】
    naver_avg_total = sum(s['distance_km'] * s['naver_speed'] for s in all_subsegments) / total_distance if total_distance > 0 else 0
    final_speed_avg = sum(s['distance_km'] * s['final_speed'] for s in all_subsegments) / total_distance if total_distance > 0 else 0
    avg_congestion = sum(congestion_list) / len(congestion_list) if congestion_list else 0
    avg_fuel = sum([s['fuel_or_h2'] for s in all_subsegments]) / len(all_subsegments) if all_subsegments else 0
    
    total_duration_hours = total_duration_ms / 3600000
    
    print("\n📊 통계 요약:")
    print(f"  ✓ 총 구간 수: {len(all_subsegments)}")
    print(f"  ✓ 총 거리: {total_distance:.2f} km")
    print(f"  ✓ 총 시간: {total_duration_ms / 60000:.1f}분 ({total_duration_hours:.2f}시간)")
    print(f"  ✓ 네이버 평균속도: {naver_avg_total:.1f} km/h")
    print(f"  ✓ Final Speed 평균: {final_speed_avg:.1f} km/h ⭐")
    
    print("\n🌍 탄소배출 분석:")
    print(f"  ✓ 총 CO2 배출: {total_co2:.2f} kg ✅ (구간별 자동 합산)")
    if total_distance > 0:
        print(f"  ✓ 평균 CO2: {total_co2 / total_distance:.4f} kg/km ⭐")
    
    if vehicle_type == "수소-대형":
        print("\n🔋 수소 분석:")
        print("  ✓ 운영 배출: 0 kg/km (전기차 수준)")
        print("  ✓ 생산 배출: get_hydrogen_co2_per_km() (적재율 함수)")
        print(f"  ✓ 평균 H2: {avg_fuel * 100:.4f} kg/100km")
    else:
        print("\n⛽ 내연기관 분석:")
        print(f"  ✓ 평균 연료: {avg_fuel:.4f} L/km")
    
    return {
        'total_distance': total_distance,
        'total_duration_hours': total_duration_hours,
        'naver_avg_speed': naver_avg_total,
        'final_speed_avg': final_speed_avg,
        'avg_congestion': avg_congestion,
        'total_co2': total_co2
    }

def analyze_route_segments(segments, vehicle_type, current_load, departure_datetime):
    """경로 구간별 분석"""
    
    specs = vehicle_reference_specs.get(vehicle_type, {})
    max_load = specs.get("max_load", 1)
    load_percent = (current_load / max_load) if max_load > 0 else 0
    load_percent = min(1.0, max(0.25, load_percent))
    
    segment_analysis = []
    current_time = departure_datetime
    
    for seg in segments:
        grade = calculate_grade(seg["start_coords"][0], seg["start_coords"][1], seg["end_coords"][0], seg["end_coords"][1], seg["distance_km"])
        
        naver_api_speed = seg["distance_km"] / (seg["duration_min"] / 60) if seg["duration_min"] > 0 else 60
        
        speed_factor = calculate_speed_factor_from_table2(vehicle_type, load_percent, grade)
        
        vehicle_speed_data = calculate_vehicle_speeds(naver_api_speed, speed_factor, grade, vehicle_type)
        final_speed = vehicle_speed_data["예상_평균속도"]
        
        duration_by_final_speed = (seg["distance_km"] / final_speed) * 60 if final_speed > 0 else seg["duration_min"]
        
        # ✅ 핵심: 운영 + 생산 분리
        operation_co2_coef = calculate_operation_co2_coefficient(vehicle_type, final_speed)
        manufacturing_co2_coef = calculate_manufacturing_co2_coefficient(vehicle_type, load_percent)
        total_co2_coef = operation_co2_coef + manufacturing_co2_coef
        
        segment_co2_emission = total_co2_coef * seg["distance_km"]
        
        arrival_time = current_time + timedelta(minutes=duration_by_final_speed)
        
        segment_analysis.append({
            **seg,
            "grade": grade,
            "naver_api_speed": naver_api_speed,
            "speed_factor": speed_factor,
            "load_percent": load_percent,
            "final_speed": final_speed,
            "vehicle_speed_data": vehicle_speed_data,
            "operation_co2_coef": operation_co2_coef,
            "manufacturing_co2_coef": manufacturing_co2_coef,
            "total_co2_coef": total_co2_coef,
            "segment_co2_emission": segment_co2_emission,
            "duration_min": duration_by_final_speed,
            "departure_time": current_time.strftime("%Y-%m-%d %H:%M"),
            "arrival_time": arrival_time.strftime("%Y-%m-%d %H:%M")
        })
        
        current_time = arrival_time
    
    return segment_analysis

def calculate_route_summary(segments):
    """경로 전체 요약"""
    total_distance_km = sum(seg["distance_km"] for seg in segments)
    total_duration_min = sum(seg["duration_min"] for seg in segments)
    total_co2_emission = sum(seg.get("segment_co2_emission", 0) for seg in segments)
    
    return {"distance_km": total_distance_km, "duration_min": total_duration_min, "co2_emission": total_co2_emission}

# ============================================================================
# 【세션 상태】
# ============================================================================

if 'route_result' not in st.session_state:
    st.session_state.route_result = None
if "start_results" not in st.session_state:
    st.session_state.start_results = []
if "goal_results" not in st.session_state:
    st.session_state.goal_results = []
if "selected_start" not in st.session_state:
    st.session_state.selected_start = None
if "selected_goal" not in st.session_state:
    st.session_state.selected_goal = None
if "temp_markers" not in st.session_state:
    st.session_state.temp_markers = {"start": None, "goal": None}
if "waypoints" not in st.session_state:
    st.session_state.waypoints = []
if "waypoint_search_results" not in st.session_state:
    st.session_state.waypoint_search_results = {}
if "selected_routes" not in st.session_state:
    st.session_state.selected_routes = {'traoptimal': True, 'trafast': True, 'tracomfort': True}
if "selected_departure_time" not in st.session_state:
    st.session_state.selected_departure_time = datetime.now().time()

# ============================================================================
# 【메인 다이얼로그】
# ============================================================================

@st.dialog("🚩 경로 분석 입력", width="large")
def route_analysis_dialog():
    st.markdown("### 📍 출발지 및 도착지")
    
    col1, col2 = st.columns(2)
    
    with col1:
        start_query = st.text_input("🔴 출발지 검색", placeholder="예: 인천대학교", key="start_search_input")
        if st.button("출발지 검색", key="btn_search_start", use_container_width=True):
            if start_query:
                with st.spinner("검색 중..."):
                    results = search_local_or_geocode(start_query)
                    st.session_state.start_results = results
                    if results:
                        st.success(f"✅ {len(results)}개 결과 발견")
                    else:
                        st.error("❌ 검색 결과 없음")
        
        if st.session_state.start_results:
            start_options = [f"{it['title'].replace('<b>','').replace('</b>','')} - {it['address'][:30]}..." for it in st.session_state.start_results]
            selected_idx = st.selectbox("출발지 선택", range(len(start_options)), format_func=lambda x: start_options[x], key="select_start_idx")
            st.session_state.selected_start = st.session_state.start_results[selected_idx]
            start_item = st.session_state.selected_start
            start_lat = float(start_item["mapy"]) / 1e7
            start_lng = float(start_item["mapx"]) / 1e7
            st.session_state.temp_markers["start"] = (start_lat, start_lng, start_item)
    
    with col2:
        goal_query = st.text_input("🔵 도착지 검색", placeholder="예: 서울역", key="goal_search_input")
        if st.button("도착지 검색", key="btn_search_goal", use_container_width=True):
            if goal_query:
                with st.spinner("검색 중..."):
                    results = search_local_or_geocode(goal_query)
                    st.session_state.goal_results = results
                    if results:
                        st.success(f"✅ {len(results)}개 결과 발견")
                    else:
                        st.error("❌ 검색 결과 없음")
        
        if st.session_state.goal_results:
            goal_options = [f"{it['title'].replace('<b>','').replace('</b>','')} - {it['address'][:30]}..." for it in st.session_state.goal_results]
            selected_idx = st.selectbox("도착지 선택", range(len(goal_options)), format_func=lambda x: goal_options[x], key="select_goal_idx")
            st.session_state.selected_goal = st.session_state.goal_results[selected_idx]
            goal_item = st.session_state.selected_goal
            goal_lat = float(goal_item["mapy"]) / 1e7
            goal_lng = float(goal_item["mapx"]) / 1e7
            st.session_state.temp_markers["goal"] = (goal_lat, goal_lng, goal_item)
    
    st.markdown("---")
    st.markdown("### 📅 출발 일시")
    col1, col2 = st.columns(2)
    with col1:
        departure_date = st.date_input("날짜", value=datetime.now().date(), key="input_date")
    with col2:
        departure_time = st.time_input("시각", value=st.session_state.selected_departure_time, key="input_time", step=300)
    
    st.markdown("---")
    st.markdown("### 🚛 차종 선택")
    vehicle_type = st.selectbox("차종 선택", ["소형", "중형", "대형", "수소-대형"], key="input_vehicle")
    
    if vehicle_type:
        specs = vehicle_reference_specs.get(vehicle_type, {})
        st.markdown("**📊 선택된 차종의 기본사양:**")
        
        if vehicle_type == "수소-대형":
            spec_col1, spec_col2, spec_col3, spec_col4 = st.columns(4)
            spec_col1.metric("🔋 연료전지", f"{specs.get('fuel_cell_kw', 0)}kW×2")
            spec_col2.metric("⚙️ 모터", f"{specs.get('motor_kw', 0)}kW")
            spec_col3.metric("📦 공차", f"{specs.get('empty_weight', 0):,}kg")
            spec_col4.metric("📦 최대적재", f"{specs.get('max_load', 0):,}kg")
        else:
            spec_col1, spec_col2, spec_col3 = st.columns(3)
            spec_col1.metric("⚙️ 엔진 출력", f"{specs.get('engine_kw', 0)} kW")
            spec_col2.metric("📦 공차 중량", f"{specs.get('empty_weight', 0):,} kg")
            spec_col3.metric("📦 최대적재량", f"{specs.get('max_load', 0):,} kg")
    
    st.markdown("---")
    st.markdown("### 📦 화물 정보")
    
    col1, col2 = st.columns(2)
    
    with col1:
        specs = vehicle_reference_specs[vehicle_type]
        max_load = specs["max_load"]
        current_load = st.number_input("현재 적재량 (kg)", min_value=0, max_value=max_load, value=0, step=50, key="input_current_load")
    
    with col2:
        load_rate = (current_load / max_load) * 100 if max_load > 0 else 0
        st.progress(load_rate / 100)
        st.write(f"**적재율: {load_rate:.1f}%**")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✖️ 취소", key="btn_cancel", use_container_width=True):
            st.session_state.temp_markers = {"start": None, "goal": None}
            st.session_state.waypoints = []
            st.session_state.waypoint_search_results = {}
            st.rerun()
    
    with col2:
        if st.button("🚀 경로 분석 실행", key="btn_analyze", type="primary", use_container_width=True):
            if not st.session_state.selected_start or not st.session_state.selected_goal:
                st.error("⚠️ 출발지와 도착지를 모두 검색하고 선택해주세요!")
            else:
                start_item = st.session_state.selected_start
                goal_item = st.session_state.selected_goal
                
                start_lng = float(start_item["mapx"]) / 1e7
                start_lat = float(start_item["mapy"]) / 1e7
                goal_lng = float(goal_item["mapx"]) / 1e7
                goal_lat = float(goal_item["mapy"]) / 1e7
                
                all_locations = [(start_lat, start_lng, start_item)]
                all_locations.extend(st.session_state.waypoints)
                all_locations.append((goal_lat, goal_lng, goal_item))
                
                try:
                    with st.spinner("경로 분석 중..."):
                        all_routes = get_all_route_types_with_guide_matching(all_locations, vehicle_type, current_load)
                        
                        if all_routes and any(all_routes.values()):
                            departure_datetime = datetime.combine(departure_date, departure_time)
                            
                            route_results = {}
                            
                            for route_type in ['traoptimal', 'trafast', 'tracomfort']:
                                segments = all_routes[route_type]
                                
                                if segments:
                                    segment_analysis = analyze_route_segments(segments, vehicle_type, current_load, departure_datetime)
                                    summary = calculate_route_summary(segment_analysis)
                                    
                                    route_results[route_type] = {
                                        'segments': segment_analysis,
                                        'total_distance_km': summary['distance_km'],
                                        'total_duration_min': summary['duration_min'],
                                        'total_co2_emission': summary['co2_emission']
                                    }
                            
                            specs = vehicle_reference_specs.get(vehicle_type, {})
                            
                            st.session_state.route_result = {
                                "vehicle_type": vehicle_type,
                                "engine_kw": specs.get('engine_kw', 0),
                                "empty_weight": specs.get('empty_weight', 0),
                                "max_load": specs.get('max_load', 0),
                                "current_load": current_load,
                                "fuel_cell_kw": specs.get('fuel_cell_kw'),
                                "motor_kw": specs.get('motor_kw'),
                                "tank_capacity": specs.get('tank_capacity'),
                                "all_locations": all_locations,
                                **route_results
                            }
                            
                            st.session_state.temp_markers = {"start": None, "goal": None}
                            st.session_state.waypoints = []
                            st.session_state.waypoint_search_results = {}
                            st.success("✅ 경로 분석 완료!")
                            st.rerun()
                        else:
                            st.error("❌ 경로를 찾을 수 없습니다.")
                except Exception as e:
                    st.error(f"❌ 오류: {str(e)}")

@st.dialog('경로 분석 결과', width='large')
def route_result_dialog():
    if st.session_state.route_result:
        result = st.session_state.route_result
        
        st.markdown('### 📊 경로 선택')
        leg_col1, leg_col2, leg_col3 = st.columns(3)
        
        with leg_col1:
            st.session_state.selected_routes['traoptimal'] = st.checkbox('🟣 최적경로', value=st.session_state.selected_routes['traoptimal'], key='cb_traoptimal')
        with leg_col2:
            st.session_state.selected_routes['trafast'] = st.checkbox('🔵 빠른경로', value=st.session_state.selected_routes['trafast'], key='cb_trafast')
        with leg_col3:
            st.session_state.selected_routes['tracomfort'] = st.checkbox('🟢 편한경로', value=st.session_state.selected_routes['tracomfort'], key='cb_tracomfort')
        
        st.markdown('---')
        
        user_lat, user_lng = get_user_location()
        m = folium.Map(location=[user_lat, user_lng], zoom_start=12, tiles='OpenStreetMap')
        
        for i, (lat, lng, info) in enumerate(result['all_locations']):
            if i == 0:
                folium.Marker([lat, lng], popup=f"<b>🔴 출발: {info['title']}</b>", icon=folium.Icon(color="red", icon="play")).add_to(m)
            elif i == len(result['all_locations']) - 1:
                folium.Marker([lat, lng], popup=f"<b>🔵 도착: {info['title']}</b>", icon=folium.Icon(color="blue", icon="stop")).add_to(m)
            else:
                folium.Marker([lat, lng], popup=f"<b>🟠 경유지 {i}: {info['title']}</b>", icon=folium.Icon(color="orange", icon="info-sign", prefix="glyphicon")).add_to(m)
        
        for route_type in ['traoptimal', 'trafast', 'tracomfort']:
            if not st.session_state.selected_routes[route_type]:
                continue
            
            if route_type not in result:
                continue
            
            route_result_data = result[route_type]
            segments_data = route_result_data.get('segments', [])
            
            for seg in segments_data:
                segment_list = seg.get('segments', [])
                
                if segment_list:
                    for subseg in segment_list:
                        path = subseg.get('path', [])
                        if not path or len(path) < 2:
                            continue
                        
                        path_coords = [[coord[1], coord[0]] for coord in path]
                        color = subseg.get('color', '#808080')
                        
                        folium.PolyLine(
                            locations=path_coords,
                            color=color,
                            weight=6,
                            opacity=0.8
                        ).add_to(m)
        
        st_folium(m, width='100%', height=600)
        
        st.markdown('### 📈 경로별 상세 정보')
        
        for route_type in ['traoptimal', 'trafast', 'tracomfort']:
            if not st.session_state.selected_routes[route_type]:
                continue
            if route_type not in result:
                continue
            
            route_result_data = result[route_type]
            
            st.markdown(f"#### 🚗 [{route_type.upper()}] 경로")
            
            load_pct = result.get('current_load', 0) / result.get('max_load', 1) if result.get('max_load', 1) > 0 else 0
            
            stats = print_segment_details_to_console(
                route_result_data,
                route_type,
                vehicle_type=result['vehicle_type'],
                load_percent=load_pct,
                grade=0
            )
            
            st.markdown("**📍 기본 경로 정보**")
            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric('거리', f"{stats['total_distance']:.2f} km")
            col2.metric('시간', f"{stats['total_duration_hours']*60:.0f}분")
            col3.metric('평균속도', f"{stats['naver_avg_speed']:.1f} km/h")
            col4.metric('Final Speed', f"{stats['final_speed_avg']:.1f} km/h ⭐")
            
            st.markdown("**🌍 환경 영향 ✅**")
            total_co2 = stats['total_co2']
            co2_col1, co2_col2 = st.columns(2)
            co2_col1.metric('CO₂ 배출량', f"{total_co2:.2f} kg")
            if stats['total_distance'] > 0:
                co2_col2.metric('CO₂ 배출계수', f"{total_co2 / stats['total_distance']:.4f} kg/km")
            else:
                co2_col2.metric('CO₂ 배출계수', "N/A")
            
            if result['vehicle_type'] == "수소-대형":
                st.markdown("**🔋 수소 정보**")
                h2_col = st.columns(1)[0]
                h2_col.metric('H2 소비율', f"{get_hydrogen_h2_consumption(load_pct):.2f} kg/100km (적재율 반영)")
            
            st.markdown("**🚛 차량 사양**")
            if result['vehicle_type'] == "수소-대형":
                col1, col2, col3, col4 = st.columns(4)
                col1.metric('🚛 차종', result.get('vehicle_type', '불명'))
                col2.metric('🔋 연료전지', f"{result.get('fuel_cell_kw', 0)}kW×2")
                col3.metric('⚙️ 모터', f"{result.get('motor_kw', 0)}kW")
                col4.metric('📦 공차', f"{result.get('empty_weight', 0):,} kg")
            else:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric('🚛 차종', result.get('vehicle_type', '불명'))
                col2.metric('⚙️ 엔진', f"{result.get('engine_kw', 0):.1f} kW")
                col3.metric('📦 공차', f"{result.get('empty_weight', 0):,} kg")
                col4.metric('📦 최대적재', f"{result.get('max_load', 0):,} kg")
            
            st.markdown("**📦 현재 적재 정보**")
            col1, col2, col3, col4 = st.columns(4)
            
            current_load = result.get('current_load', 0)
            max_load = result.get('max_load', 0)
            load_rate = (current_load / max_load) * 100 if max_load > 0 else 0
            total_weight = result.get('empty_weight', 0) + current_load
            engine_kw = result.get('engine_kw', 0)
            power_to_weight = total_weight / engine_kw if engine_kw > 0 else 0
            
            col1.metric('📦 현재 적재량', f"{current_load:,} kg")
            col2.metric('📊 적재율', f"{load_rate:.1f}%")
            col3.metric('⚖️ 총 중량', f"{total_weight:,} kg")
            col4.metric('⚙️ 무게-마력비', f"{power_to_weight:.2f} kg/kW")
            
            st.divider()

# ============================================================================
# 【메인 화면】
# ============================================================================

st.title("🚚 친환경 물류 경로 시뮬레이션")

col1, col2, col3, col4, spacer = st.columns([1, 1, 1, 1, 4])
with col1:
    if st.button("🚩 경로분석", type="primary", key="btn_open_dialog"):
        route_analysis_dialog()
with col2:
    if st.session_state.route_result:
        if st.button("📋 결과보기", key="btn_show_result"):
            route_result_dialog()
    else:
        st.button("📋 결과보기", disabled=True)

user_lat, user_lng = get_user_location()
m = folium.Map(location=[user_lat, user_lng], zoom_start=12, tiles="OpenStreetMap")
folium.Marker([user_lat, user_lng], popup="📍 현재 위치", icon=folium.Icon(color="green", icon="user")).add_to(m)

if st.session_state.temp_markers["start"]:
    start_lat, start_lng, start_item = st.session_state.temp_markers["start"]
    folium.Marker([start_lat, start_lng], popup=f"<b>{start_item['title']}</b>", icon=folium.Icon(color="red", icon="play")).add_to(m)
    m.location = [start_lat, start_lng]

if st.session_state.temp_markers["goal"]:
    goal_lat, goal_lng, goal_item = st.session_state.temp_markers["goal"]
    folium.Marker([goal_lat, goal_lng], popup=f"<b>{goal_item['title']}</b>", icon=folium.Icon(color="blue", icon="stop")).add_to(m)
    
    if st.session_state.temp_markers["start"]:
        m.fit_bounds([[start_lat, start_lng], [goal_lat, goal_lng]], padding=[50, 50])

if st.session_state.route_result:
    result = st.session_state.route_result
    
    for route_type in ['traoptimal', 'trafast', 'tracomfort']:
        if route_type not in result:
            continue
        
        route_result_data = result[route_type]
        segments = route_result_data.get('segments', [])
        
        for seg in segments:
            segment_list = seg.get('segments', [])
            
            if segment_list:
                for subseg in segment_list:
                    path = subseg.get('path', [])
                    if not path or len(path) < 2:
                        continue
                    
                    path_coords = [[coord[1], coord[0]] for coord in path]
                    color = subseg.get('color', '#808080')
                    
                    folium.PolyLine(
                        locations=path_coords,
                        color=color,
                        weight=6,
                        opacity=0.8
                    ).add_to(m)
    
    for i, (lat, lng, info) in enumerate(result['all_locations']):
        if i == 0:
            folium.Marker([lat, lng], popup=f"<b>🔴 출발: {info['title']}</b>", icon=folium.Icon(color="red", icon="play")).add_to(m)
        elif i == len(result['all_locations']) - 1:
            folium.Marker([lat, lng], popup=f"<b>🔵 도착: {info['title']}</b>", icon=folium.Icon(color="blue", icon="stop")).add_to(m)
        else:
            folium.Marker([lat, lng], popup=f"<b>🟠 경유지 {i}: {info['title']}</b>", icon=folium.Icon(color="orange", icon="info-sign", prefix="glyphicon")).add_to(m)
    
    all_coords = result['all_locations']
    m.fit_bounds([[coord[0], coord[1]] for coord in all_coords], padding=[50, 50])


st_folium(m, width="100%", height=1200, key="main_map")
