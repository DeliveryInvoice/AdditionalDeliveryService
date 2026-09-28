import time
import secrets
from io import BytesIO
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

import threading

import av
import cv2
import numpy as np
import qrcode
import streamlit as st
from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer

st.set_page_config(page_title="배송 확인 시스템")

DRIVERS = {
    "D001": {"pw": "1234", "name": "김기사"},
    "D002": {"pw": "5678", "name": "이기사"},
}


@st.cache_resource
def load_orders():
    return {
        "ORD001": {
            "pw": "9999",
            "buyer": "홍길동",
            "buyer_email": "hong@example.com",
            "address": "서울시 강남구 xx로 123",
            "location": "서울시 강남구 xx로",
            "status": "배송중",
        },
        "ORD002": {
            "pw": "1111",
            "buyer": "김xx",
            "buyer_email": "kim@example.com",
            "address": "서울시 마포구 궁동 456",
            "location": "서울시 마포구 궁동로",
            "status": "배송완료",
        },
    }


ORDERS = load_orders()
KST = timezone(timedelta(hours=9))

EXPIRE_MINUTES = {
    "5분": 5,
    "30분": 30,
    "1시간": 60,
    "6시간": 360,
    "12시간": 720,
    "24시간": 1440,
    "48시간": 2880,
}


def go(page):
    st.session_state.page = page
    st.rerun()


def expired(order):
    expires_at = order.get("expires_at")
    if not expires_at:
        return False
    return datetime.now(KST) >= datetime.fromisoformat(expires_at)


def fmt_minutes(total):
    days, rest = divmod(total, 1440)
    hours, minutes = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    return " ".join(parts)


def remaining(order):
    expires_at = order.get("expires_at")
    if not expires_at:
        # 아직 배송 완료 전: 만료 시간은 배송 완료 후부터 계산됨
        if order.get("expire_minutes"):
            return f'배송 완료 후 {fmt_minutes(order["expire_minutes"])} 동안 공개'
        return None

    seconds = int(
        (datetime.fromisoformat(expires_at) - datetime.now(KST)).total_seconds()
    )

    if seconds <= 0:
        return "만료되었습니다."

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}일 {hours}시간 {minutes}분"
    if hours:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분 {seconds}초"


# ---------------------------------------------------------------
# QR 관련 함수
# ---------------------------------------------------------------
def make_qr(data):
    qr = qrcode.make(data)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()


def build_qr_text(order_id, order):
    """QR②: 주문정보를 글로 저장할 내용"""
    return (
        f"주문번호: {order_id}\n"
        f"구매자: {order['buyer']}\n"
        f"주소: {order['address']}\n"
        f"물품: {order.get('product', '')}\n"
        f"수량: {order.get('quantity', '')}\n"
        f"인증코드: {order.get('token', '')}"
    )


def parse_qr_text(text):
    data = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data


def decode_qr(image_file):
    """카메라 사진에서 QR 내용을 읽음"""
    arr = np.frombuffer(image_file.getvalue(), np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return ""
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(frame)
    return text


def verify_parcel(text, my_oid):
    """찍은 QR②가 로그인한 구매자의 주문과 일치하는지 확인"""
    data = parse_qr_text(text)
    order = ORDERS.get(my_oid)
    if not order:
        return False

    if data.get("주문번호", "").upper() != my_oid:
        return False
    if data.get("구매자") != order["buyer"]:
        return False
    if data.get("주소") != order["address"]:
        return False
    if "product" in order and data.get("물품") != order["product"]:
        return False
    if "quantity" in order and data.get("수량") != str(order["quantity"]):
        return False
    if order.get("token") and data.get("인증코드") != order["token"]:
        return False
    return True


class QRProcessor(VideoProcessorBase):
    """후면 카메라 영상에서 QR을 실시간으로 읽는 처리기"""

    def __init__(self):
        self.detector = cv2.QRCodeDetector()
        self.lock = threading.Lock()
        self.text = None
        self.last_check = 0.0

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        now = time.time()
        if now - self.last_check > 0.3:  # 0.3초마다 한 번만 검사
            self.last_check = now
            text, _, _ = self.detector.detectAndDecode(img)
            if text:
                with self.lock:
                    self.text = text
        return av.VideoFrame.from_ndarray(img, format="bgr24")


def show_extra(order):
    if "product" in order:
        st.write("**구매 물품:**", order["product"])
    if "quantity" in order:
        st.write("**수량:**", f'{order["quantity"]}개')
    if "price" in order:
        st.write("**가격:**", f'{order["price"]:,}원')
    time_left = remaining(order)
    if time_left:
        st.write("**남은 정보 공개시간:**", time_left)


def show_expired():
    st.error("정보 열람 가능 시간이 만료되었습니다.")
    st.warning("개인정보 보호를 위해 주문 상세정보가 비공개 처리되었습니다.")


# ---------------------------------------------------------------
# 세션 초기화
# ---------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "menu"
if "driver" not in st.session_state:
    st.session_state.driver = None
if "generated" not in st.session_state:
    st.session_state.generated = None
if "driver_order_id" not in st.session_state:
    st.session_state.driver_order_id = None
if "buyer_oid" not in st.session_state:
    st.session_state.buyer_oid = None  # 로그인한 주문번호
if "buyer_step" not in st.session_state:
    st.session_state.buyer_step = "login"  # login → scan → result
if "cam_key" not in st.session_state:
    st.session_state.cam_key = 0  # 카메라 초기화용


def reset_buyer():
    st.session_state.buyer_oid = None
    st.session_state.buyer_step = "login"


st.title("배송 확인 시스템")

# ---------------------------------------------------------------
# 메뉴
# ---------------------------------------------------------------
if st.session_state.page == "menu":
    st.subheader("메뉴")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("배송기사", use_container_width=True):
            go("driver_login")
    with col2:
        if st.button("구매자", use_container_width=True):
            reset_buyer()
            go("buyer_login")
    with col3:
        if st.button("판매자", use_container_width=True):
            go("seller")

    st.divider()
    if st.button("주문번호 찾기", use_container_width=True):
        go("find_order")

# ---------------------------------------------------------------
# 주문번호 찾기
# ---------------------------------------------------------------
elif st.session_state.page == "find_order":
    st.subheader("주문번호 찾기")
    st.write("주문할 때 입력한 이름과 이메일을 입력해주세요.")

    with st.form("find_order_form"):
        find_name = st.text_input("구매자 이름")
        find_email = st.text_input("구매자 이메일")
        find = st.form_submit_button("주문번호 찾기", use_container_width=True)

    if find:
        find_name = find_name.strip()
        find_email = find_email.strip().lower()

        found_orders = []
        for oid, order in ORDERS.items():
            same_name = order.get("buyer", "").strip() == find_name
            same_email = order.get("buyer_email", "").strip().lower() == find_email

            if same_name and same_email:
                found_orders.append(oid)

        if not find_name or not find_email:
            st.warning("이름과 이메일을 모두 입력해주세요.")
        elif found_orders:
            st.success("주문번호를 찾았습니다.")
            for oid in found_orders:
                st.write(f"### {oid}")
        else:
            st.error("입력한 정보와 일치하는 주문이 없습니다.")

    if st.button("메인 메뉴로", use_container_width=True):
        go("menu")

# ---------------------------------------------------------------
# 판매자: 주문 등록 + QR 2개 생성
# ---------------------------------------------------------------
elif st.session_state.page == "seller":
    st.subheader("판매자 주문 등록 및 QR코드 생성")

    with st.form("seller_form"):
        order_id = st.text_input("주문번호", placeholder="ORD003")
        buyer = st.text_input("구매자 이름", placeholder="홍길동")
        buyer_email = st.text_input(
            "구매자 이메일", placeholder="example@email.com"
        )
        address = st.text_input("배송 주소", placeholder="00시 00구 000로 123")
        product = st.text_input("구매 물품", placeholder="무선 이어폰")
        quantity = st.number_input("수량", min_value=1, value=1)
        price = st.number_input("가격", min_value=0, step=1000)
        password = st.text_input("구매자 비밀번호", type="password")

        expire_option = st.selectbox(
            "정보 공개시간", list(EXPIRE_MINUTES), index=5
        )
        app_url = st.text_input(
            "QR생성용 링크(입력된 정보를 포함해요)",
            value="https://additionalservice.streamlit.app",
        )
        submitted = st.form_submit_button(
            "주문 등록 및 QR코드 생성", use_container_width=True
        )

    if submitted:
        order_id = order_id.strip().upper()
        buyer = buyer.strip()
        buyer_email = buyer_email.strip()
        address = address.strip()
        location = address
        product = product.strip()
        password = password.strip()
        app_url = app_url.strip().rstrip("/")

        inputs = [order_id, buyer, buyer_email, address, product, password, app_url]

        if not all(inputs):
            st.error("모든 항목을 입력해주세요.")
        elif order_id in ORDERS:
            st.error("이미 등록된 주문번호입니다.")
        else:
            token = secrets.token_urlsafe(16)

            ORDERS[order_id] = {
                "pw": password,
                "buyer": buyer,
                "buyer_email": buyer_email,
                "address": address,
                "location": location,
                "product": product,
                "quantity": int(quantity),
                "price": int(price),
                "status": "배송준비",
                "token": token,
                # 배송 완료 시점부터 계산하므로 지금은 시간만 저장
                "expire_minutes": EXPIRE_MINUTES[expire_option],
            }

            qr_url = f"{app_url}?order={quote(order_id)}&token={quote(token)}"
            qr_text = build_qr_text(order_id, ORDERS[order_id])

            st.session_state.generated = {
                "order_id": order_id,
                "url": qr_url,
                "image": make_qr(qr_url),  # QR① 접속 링크
                "text": qr_text,
                "text_image": make_qr(qr_text),  # QR② 주문정보 글
            }

            st.success("주문과 QR코드 2개가 생성되었습니다.")

    generated = st.session_state.generated

    if generated:
        order = ORDERS.get(generated["order_id"])
        if order:
            st.divider()
            st.write("### 생성 결과")
            st.write("**주문번호:**", generated["order_id"])
            st.write("**구매자:**", order["buyer"])
            st.write("**주소:**", order["address"])
            st.write("**배송 위치:**", order["location"])
            show_extra(order)
            st.write("**상태:**", order["status"])

            col1, col2 = st.columns(2)

            with col1:
                st.image(
                    generated["image"],
                    caption="QR① 주문 조회용 (링크)",
                    use_container_width=True,
                )
                st.download_button(
                    "QR① 저장",
                    generated["image"],
                    file_name=f'{generated["order_id"]}_QR_link.png',
                    mime="image/png",
                    use_container_width=True,
                )

            with col2:
                st.image(
                    generated["text_image"],
                    caption="QR② 택배 확인용 (주문정보 글)",
                    use_container_width=True,
                )
                st.download_button(
                    "QR② 저장",
                    generated["text_image"],
                    file_name=f'{generated["order_id"]}_QR_text.png',
                    mime="image/png",
                    use_container_width=True,
                )

            with st.expander("QR① 접속 주소"):
                st.code(generated["url"])
            with st.expander("QR② 저장된 글 내용"):
                st.code(generated["text"])

    if st.button("메인 메뉴로", use_container_width=True):
        go("menu")

# ---------------------------------------------------------------
# 배송기사
# ---------------------------------------------------------------
elif st.session_state.page == "driver_login":
    st.subheader("배송기사 로그인")

    driver_id = st.text_input("기사번호", placeholder="D001")
    password = st.text_input("비밀번호", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("로그인", use_container_width=True):
            driver = DRIVERS.get(driver_id.strip().upper())
            if driver and driver["pw"] == password:
                st.session_state.driver = driver
                go("driver_dashboard")
            else:
                st.error("인증 실패")
    with col2:
        if st.button("취소", use_container_width=True):
            go("menu")

elif st.session_state.page == "driver_dashboard":
    driver = st.session_state.driver
    if not driver:
        go("driver_login")

    st.subheader(f'대시보드 - {driver["name"]}님')
    order_id = st.text_input(
        "주문번호",
        value=st.query_params.get("order", ""),
    )

    col1, col2 = st.columns(2)

    with col1:
        search = st.button("조회", use_container_width=True)
    with col2:
        logout = st.button("로그아웃", use_container_width=True)

    if logout:
        st.session_state.driver = None
        st.session_state.driver_order_id = None
        go("menu")

    if search:
        searched_id = order_id.strip().upper()
        order = ORDERS.get(searched_id)

        if not order:
            st.session_state.driver_order_id = None
            st.warning("주문이 없습니다.")
        elif expired(order):
            st.session_state.driver_order_id = None
            show_expired()
        else:
            st.session_state.driver_order_id = searched_id

    # 조회한 주문을 세션에 저장해 두어 버튼을 눌러도 화면이 유지됨
    current_id = st.session_state.driver_order_id

    if current_id:
        order = ORDERS.get(current_id)

        if order:
            st.write("### 주문 정보")
            st.write("**주문번호:**", current_id)
            st.write("**수령인:**", order["buyer"])
            st.write("**주소:**", order["address"])
            st.write("**배송 위치:**", order["location"])
            show_extra(order)
            st.write("**상태:**", order["status"])

            map_url = "https://map.kakao.com/link/search/" f"{quote(order['address'])}"
            st.link_button("카카오맵에서 보기", map_url, use_container_width=True)

            if order["status"] != "배송완료":
                if st.button("배송 완료", type="primary", use_container_width=True):
                    now = datetime.now(KST)
                    order["status"] = "배송완료"
                    order["completed_at"] = now.isoformat()
                    if order.get("expire_minutes"):
                        order["expires_at"] = (
                            now + timedelta(minutes=order["expire_minutes"])
                        ).isoformat()
                    st.success("배송 상태가 '배송완료'로 변경되었습니다.")
                    st.rerun()
            else:
                st.success("배송이 완료된 주문입니다.")

# ---------------------------------------------------------------
# 구매자: 주문번호+비밀번호 → QR로 찾기 → QR② 스캔 → 배송정보
# ---------------------------------------------------------------
elif st.session_state.page == "buyer_login":
    st.subheader("구매자 조회")
    step = st.session_state.buyer_step

    # ---------- 1단계: 주문번호 + 비밀번호 ----------
    if step == "login":
        order_id = st.text_input(
            "주문번호",
            value=st.query_params.get("order", ""),
        )
        password = st.text_input("비밀번호", type="password")

        col1, col2 = st.columns(2)
        with col1:
            find = st.button("QR로 찾기", type="primary", use_container_width=True)
        with col2:
            if st.button("취소", use_container_width=True):
                go("menu")

        if find:
            oid = order_id.strip().upper()
            order = ORDERS.get(oid)

            if not order or order["pw"] != password:
                st.error("인증 실패")
            elif expired(order):
                show_expired()
            else:
                st.session_state.buyer_oid = oid
                st.session_state.buyer_step = "scan"
                st.session_state.cam_key += 1
                st.rerun()

    # ---------- 2단계: QR 스캔 (후면 카메라, 실시간) ----------
    elif step == "scan":
        my_oid = st.session_state.buyer_oid
        st.write(
            "택배에 붙은 **주문정보 QR코드(QR②)**를 "
            "후면 카메라에 갖다 대기만 하세요. 자동으로 인식합니다."
        )

        if st.button("처음으로", use_container_width=True):
            reset_buyer()
            st.rerun()

        ctx = webrtc_streamer(
            key="qr-scan",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=QRProcessor,
            media_stream_constraints={
                "video": {"facingMode": {"ideal": "environment"}},  # 후면 카메라
                "audio": False,
            },
            rtc_configuration={
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            },
            async_processing=True,
            desired_playing_state=True,  # 화면이 열리면 카메라 자동 시작
        )

        last_toast = 0.0
        while ctx.state.playing:
            proc = ctx.video_processor
            if proc:
                with proc.lock:
                    text = proc.text
                    proc.text = None

                if text:
                    if verify_parcel(text, my_oid):
                        st.session_state.buyer_step = "result"
                        st.rerun()
                    elif time.time() - last_toast > 3:
                        # 틀리면 알림만 잠깐 띄우고 계속 스캔
                        st.toast("고객님의 택배가 아닙니다.", icon="❌")
                        last_toast = time.time()
            time.sleep(0.3)

    # ---------- 3단계: 배송정보 ----------
    elif step == "result":
        my_oid = st.session_state.buyer_oid
        order = ORDERS.get(my_oid)

        if not order or expired(order):
            reset_buyer()
            show_expired()
        else:
            st.success("✅ 고객님의 택배가 맞습니다!")
            st.write("### 배송 정보")
            st.write("**주문번호:**", my_oid)
            st.write("**수령인:**", order["buyer"])
            masked = " ".join(order["address"].split()[:3]) + " ***"
            st.write("**주소:**", masked)
            show_extra(order)
            st.write("**상태:**", order["status"])

        if st.button("완료 (메인 메뉴로)", use_container_width=True):
            reset_buyer()
            go("menu")
