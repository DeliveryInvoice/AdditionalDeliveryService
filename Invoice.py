import streamlit as st
import qrcode
import secrets

from io import BytesIO
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

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
            "address": "서울시 강남구 xx로 123",
            "location": "서울시 강남구 xx로",
            "status": "배송중",
        },
        "ORD002": {
            "pw": "1111",
            "buyer": "김xx",
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

def remaining(order):
    expires_at = order.get("expires_at")
    if not expires_at:
        return None

    seconds = int(
        (
            datetime.fromisoformat(expires_at)
            - datetime.now(KST)
        ).total_seconds()
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

def make_qr(url):
    qr = qrcode.make(url)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()

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

if "page" not in st.session_state:
    st.session_state.page = "menu"
if "driver" not in st.session_state:
    st.session_state.driver = None
if "generated" not in st.session_state:
    st.session_state.generated = None

st.title("배송 확인 시스템")

if st.session_state.page == "menu":
    st.subheader("메뉴")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("배송기사", use_container_width=True):
            go("driver_login")
    with col2:
        if st.button("구매자", use_container_width=True):
            go("buyer_login")
    with col3:
        if st.button("판매자", use_container_width=True):
            go("seller")

elif st.session_state.page == "seller":
    st.subheader("판매자 주문 등록 및 QR코드 생성")

    with st.form("seller_form"):
        order_id = st.text_input("주문번호", placeholder="ORD003")
        buyer = st.text_input("구매자 이름", placeholder="홍길동")
        address = st.text_input(
            "배송 주소",
            placeholder="00시 00구 000로 123",
        )
        product = st.text_input("구매 물품", placeholder="무선 이어폰")
        quantity = st.number_input("수량", min_value=1, value=1)
        price = st.number_input("가격", min_value=0, step=1000)
        password = st.text_input("구매자 비밀번호", type="password")

        expire_option = st.selectbox(
            "정보 공개시간",
            list(EXPIRE_MINUTES),
            index=5,
        )
        app_url = st.text_input(
            "QR생성용 링크(입력된 정보를 포함해요)",
            value="https://additionalservice.streamlit.app",
        )
        submitted = st.form_submit_button(
            "주문 등록 및 QR코드 생성",
            use_container_width=True,
        )

    if submitted:
        order_id = order_id.strip().upper()
        buyer = buyer.strip()
        address = address.strip()
        location = address
        product = product.strip()
        password = password.strip()
        app_url = app_url.strip().rstrip("/")

        inputs = [
            order_id,
            buyer,
            address,
            product,
            password,
            app_url,
        ]

        if not all(inputs):
            st.error("모든 항목을 입력해주세요.")
        elif order_id in ORDERS:
            st.error("이미 등록된 주문번호입니다.")
        else:
            token = secrets.token_urlsafe(16)

            ORDERS[order_id] = {
                "pw": password,
                "buyer": buyer,
                "address": address,
                "location": location,
                "product": product,
                "quantity": int(quantity),
                "price": int(price),
                "status": "배송준비",
                "token": token,
                "expires_at": (
                    datetime.now(KST)
                    + timedelta(minutes=EXPIRE_MINUTES[expire_option])
                ).isoformat(),
            }

            qr_url = (
                f"{app_url}?order={quote(order_id)}"
                f"&token={quote(token)}"
            )

            st.session_state.generated = {
                "order_id": order_id,
                "url": qr_url,
                "image": make_qr(qr_url),
            }

            st.success("주문과 QR코드가 생성되었습니다.")

    generated = st.session_state.generated

    if generated:
        order = ORDERS.get(generated["order_id"])
        if order:
            st.divider()

            col1, col2 = st.columns(2)

            with col1:
                st.write("### 생성 결과")
                st.write("**주문번호:**", generated["order_id"])
                st.write("**구매자:**", order["buyer"])
                st.write("**주소:**", order["address"])
                st.write("**배송 위치:**", order["location"])
                show_extra(order)
                st.write("**상태:**", order["status"])

            with col2:
                st.image(
                    generated["image"],
                    caption="주문 QR코드",
                    use_container_width=True,
                )

                st.download_button(
                    "QR코드 저장",
                    generated["image"],
                    file_name=f'{generated["order_id"]}_QR.png',
                    mime="image/png",
                    use_container_width=True,
                )

            with st.expander("QR코드 접속 주소"):
                st.code(generated["url"])

    if st.button("메인 메뉴로", use_container_width=True):
        go("menu")

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
        go("menu")

    if search:
        order = ORDERS.get(order_id.strip().upper())

        if not order:
            st.warning("주문이 없습니다.")
        elif expired(order):
            show_expired()
        else:
            st.write("### 주문 정보")
            st.write("**수령인:**", order["buyer"])
            st.write("**주소:**", order["address"])
            st.write("**배송 위치:**", order["location"])
            show_extra(order)
            st.write("**상태:**", order["status"])

            map_url = (
                "https://www.google.com/maps/search/"
                f"?api=1&query={quote(order['location'])}"
            )
            st.link_button(
                " 지도에서 보기",
                map_url,
                use_container_width=True,
            )

elif st.session_state.page == "buyer_login":
    st.subheader("구매자 조회")

    order_id = st.text_input(
        "주문번호",
        value=st.query_params.get("order", ""),
    )
    password = st.text_input("비밀번호", type="password")
    col1, col2 = st.columns(2)

    with col1:
        search = st.button("조회", use_container_width=True)
    with col2:
        if st.button("취소", use_container_width=True):
            go("menu")

    if search:
        order_id = order_id.strip().upper()
        order = ORDERS.get(order_id)

        if not order or order["pw"] != password:
            st.error("인증 실패")
        elif expired(order):
            show_expired()
        else:
            masked_address = (
                " ".join(order["address"].split()[:3])
                + " ***"
            )

            st.success("조회 완료")
            st.write("### 주문 정보")
            st.write("**주문번호:**", order_id)
            st.write("**수령인:**", order["buyer"])
            st.write("**주소:**", masked_address)
            show_extra(order)
            st.write("**상태:**", order["status"])
            st.caption("! 상세주소는 보안상 가려집니다. !")
