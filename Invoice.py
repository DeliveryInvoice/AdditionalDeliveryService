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

ORDERS = {
    "ORD001": {
        "pw": "9999",
        "buyer": "홍길동",
        "address": "서울시 강남구 아무데나로 123",
        "lat": 37.5065,
        "lon": 127.0536,
        "status": "배송중",
    },
    "ORD002": {
        "pw": "1111",
        "buyer": "이순신",
        "address": "서울시 마포구 궁동 456",
        "lat": 37.5450,
        "lon": 126.9514,
        "status": "배송완료",
    },
}



@st.cache_resource
def get_shared_orders():
    """
    판매자가 생성한 주문을 다른 브라우저에서도 조회할 수 있도록
    서버 메모리에 주문정보를 저장합니다.

    단, Streamlit 서버가 완전히 재시작되면 추가 주문은 사라집니다.
    """
    return ORDERS


ORDERS = get_shared_orders()


KST = timezone(timedelta(hours=9))


def is_expired(order):
    """
    주문의 유효시간이 지났는지 확인합니다.

    기존 ORD001, ORD002처럼 expires_at이 없는 주문은
    만료되지 않은 것으로 처리합니다.
    """
    expires_at_text = order.get("expires_at")

    if not expires_at_text:
        return False

    try:
        expires_at = datetime.fromisoformat(expires_at_text)
        return datetime.now(KST) >= expires_at

    except (TypeError, ValueError):
        return False


def get_remaining_time(order):
    """
    주문정보를 볼 수 있는 남은 시간을 반환합니다.
    """
    expires_at_text = order.get("expires_at")

    if not expires_at_text:
        return None

    try:
        expires_at = datetime.fromisoformat(expires_at_text)
        remaining = expires_at - datetime.now(KST)

        if remaining.total_seconds() <= 0:
            return "만료됨"

        total_seconds = int(remaining.total_seconds())

        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{days}일 {hours}시간 {minutes}분"

        if hours > 0:
            return f"{hours}시간 {minutes}분"

        return f"{minutes}분 {seconds}초"

    except (TypeError, ValueError):
        return None


def show_expired_message():
    """
    만료된 주문에 공통으로 표시할 안내문입니다.
    """
    st.error("⏰ 정보 열람 시간이 만료되었습니다.")
    st.warning(
        "개인정보 보호를 위해 해당 주문의 구매자 이름, 주소, "
        "구매 물품, 위치, 가격 및 수량 정보가 비공개 처리되었습니다."
    )

def make_qr_code(qr_content):
    """
    전달받은 주소 또는 문자열을 QR코드 이미지로 변환합니다.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )

    qr.add_data(qr_content)
    qr.make(fit=True)

    qr_image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer

if "page" not in st.session_state:
    st.session_state.page = "menu"

if "driver" not in st.session_state:
    st.session_state.driver = None


if "generated_qr" not in st.session_state:
    st.session_state.generated_qr = None

if "generated_order_id" not in st.session_state:
    st.session_state.generated_order_id = None

if "generated_qr_content" not in st.session_state:
    st.session_state.generated_qr_content = None



def go(page):
    st.session_state.page = page
    st.rerun()


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

    st.info(
        "주문정보를 입력하면 주문번호가 포함된 QR코드가 생성됩니다. "
        "설정한 시간이 지나면 기사와 구매자가 로그인해도 "
        "주문 상세정보가 표시되지 않습니다."
    )

    with st.form("seller_order_form"):

        order_id = st.text_input(
            "주문번호",
            placeholder="예: ORD003",
        )

        buyer = st.text_input(
            "구매자 이름",
            placeholder="예: 홍길동",
        )

        address = st.text_input(
            "주소",
            placeholder="예: 서울시 강남구 아무데나로 123",
        )

        product = st.text_input(
            "구매 물품",
            placeholder="예: 무선 이어폰",
        )

        quantity = st.number_input(
            "수량",
            min_value=1,
            step=1,
            value=1,
        )

        price = st.number_input(
            "가격",
            min_value=0,
            step=1000,
            value=0,
            format="%d",
        )

        st.write("#### 배송 위치")

        lat = st.number_input(
            "위도",
            value=37.5665,
            format="%.6f",
        )

        lon = st.number_input(
            "경도",
            value=126.9780,
            format="%.6f",
        )

        buyer_pw = st.text_input(
            "구매자 조회 비밀번호",
            type="password",
            placeholder="구매자가 사용할 비밀번호",
        )

        expiration_option = st.selectbox(
            "정보 공개 유지시간",
            [
                "5분 - 시연용",
                "30분",
                "1시간",
                "6시간",
                "12시간",
                "24시간",
                "48시간",
            ],
            index=5,
        )

        app_url = st.text_input(
            "배포된 Streamlit 앱 주소",
            value="https://your-app.streamlit.app",
            help=(
                "QR코드를 촬영했을 때 접속할 앱 주소입니다. "
                "Streamlit Cloud에서 배포한 실제 주소로 변경하세요."
            ),
        )

        submitted = st.form_submit_button(
            "주문 등록 및 QR코드 생성",
            use_container_width=True,
        )

    if submitted:

        order_id = order_id.strip().upper()
        buyer = buyer.strip()
        address = address.strip()
        product = product.strip()
        buyer_pw = buyer_pw.strip()
        app_url = app_url.strip().rstrip("/")

        required_values = [
            order_id,
            buyer,
            address,
            product,
            buyer_pw,
            app_url,
        ]

        if not all(required_values):
            st.error("모든 필수 항목을 입력해주세요.")

        elif order_id in ORDERS:
            st.error("이미 등록된 주문번호입니다.")

        elif app_url == "https://your-app.streamlit.app":
            st.error(
                "배포된 Streamlit 앱 주소를 실제 주소로 변경해주세요."
            )

        else:
            expiration_minutes = {
                "5분 - 시연용": 5,
                "30분": 30,
                "1시간": 60,
                "6시간": 360,
                "12시간": 720,
                "24시간": 1440,
                "48시간": 2880,
            }

            created_at = datetime.now(KST)

            expires_at = created_at + timedelta(
                minutes=expiration_minutes[expiration_option]
            )

            secure_token = secrets.token_urlsafe(16)

            ORDERS[order_id] = {
                "pw": buyer_pw,
                "buyer": buyer,
                "address": address,
                "product": product,
                "quantity": int(quantity),
                "price": int(price),
                "lat": float(lat),
                "lon": float(lon),
                "status": "배송준비",
                "token": secure_token,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }

            qr_content = (
                f"{app_url}"
                f"?order={quote(order_id)}"
                f"&token={quote(secure_token)}"
            )

            qr_buffer = make_qr_code(qr_content)
            qr_bytes = qr_buffer.getvalue()

            st.session_state.generated_qr = qr_bytes
            st.session_state.generated_order_id = order_id
            st.session_state.generated_qr_content = qr_content

            st.success("주문정보와 QR코드가 생성되었습니다.")

    if st.session_state.generated_qr is not None:

        generated_order_id = st.session_state.generated_order_id
        generated_order = ORDERS.get(generated_order_id)

        if generated_order is not None:

            st.divider()

            st.write("### 생성 결과")

            col1, col2 = st.columns(2)

            with col1:
                st.write(
                    "**주문번호:**",
                    generated_order_id,
                )
                st.write(
                    "**구매자:**",
                    generated_order["buyer"],
                )
                st.write(
                    "**구매 물품:**",
                    generated_order["product"],
                )
                st.write(
                    "**수량:**",
                    f'{generated_order["quantity"]}개',
                )
                st.write(
                    "**가격:**",
                    f'{generated_order["price"]:,}원',
                )
                st.write(
                    "**주소:**",
                    generated_order["address"],
                )
                st.write(
                    "**좌표:**",
                    (
                        f'{generated_order["lat"]}, '
                        f'{generated_order["lon"]}'
                    ),
                )
                st.write(
                    "**상태:**",
                    generated_order["status"],
                )

                remaining_time = get_remaining_time(generated_order)

                if remaining_time:
                    st.write(
                        "**남은 정보 공개시간:**",
                        remaining_time,
                    )

            with col2:
                st.image(
                    st.session_state.generated_qr,
                    caption=f"{generated_order_id} 주문 QR코드",
                    use_container_width=True,
                )

                st.download_button(
                    "QR코드 저장",
                    data=st.session_state.generated_qr,
                    file_name=f"{generated_order_id}_QR.png",
                    mime="image/png",
                    use_container_width=True,
                )

            with st.expander("QR코드에 저장된 접속 주소"):
                st.code(
                    st.session_state.generated_qr_content,
                    language=None,
                )

    if st.button("메인 메뉴로", use_container_width=True):
        go("menu")

elif st.session_state.page == "driver_login":

    st.subheader("배송기사 로그인")

    did = st.text_input("기사번호", placeholder="D001")
    dpw = st.text_input("비밀번호", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("로그인", use_container_width=True):
            driver = DRIVERS.get(did)

            if driver and driver["pw"] == dpw:
                st.session_state.driver = driver
                go("driver_dashboard")
            else:
                st.error("인증 실패")

    with col2:
        if st.button("취소", use_container_width=True):
            go("menu")


elif st.session_state.page == "driver_dashboard":

    st.subheader(f"대시보드 - {st.session_state.driver['name']}님")

    qr_order_id = st.query_params.get("order", "")

    oid = st.text_input(
        "주문번호",
        value=qr_order_id,
        placeholder="ORD001",
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

        order = ORDERS.get(oid)

        if order is None:
            st.warning("주문이 없습니다.")

        elif is_expired(order):
            show_expired_message()

        else:
            st.write("### 주문 정보")

            st.write("**수령인:**", order["buyer"])
            st.write("**주소:**", order["address"])
            if "product" in order:
                st.write("**구매 물품:**", order["product"])

            if "quantity" in order:
                st.write("**수량:**", f'{order["quantity"]}개')

            if "price" in order:
                st.write("**가격:**", f'{order["price"]:,}원')


            st.write("**좌표:**", f'{order["lat"]}, {order["lon"]}')
            st.write("**상태:**", order["status"])


            remaining_time = get_remaining_time(order)

            if remaining_time:
                st.write(
                    "**남은 정보 공개시간:**",
                    remaining_time,
                )

            map_url = (
                f"https://maps.google.com/"
                f"?q={order['lat']},{order['lon']}"
            )

            st.link_button("🗺 지도 보기", map_url)

            st.map(
                [{"lat": order["lat"], "lon": order["lon"]}],
                zoom=12,
            )


elif st.session_state.page == "buyer_login":

    st.subheader("구매자 조회")


    qr_order_id = st.query_params.get("order", "")

    oid = st.text_input(
        "주문번호",
        value=qr_order_id,
        placeholder="ORD001",
    )


    pw = st.text_input("비밀번호", type="password")

    col1, col2 = st.columns(2)

    with col1:
        search = st.button("조회", use_container_width=True)

    with col2:
        cancel = st.button("취소", use_container_width=True)

    if cancel:
        go("menu")

    if search:

        order = ORDERS.get(oid)

        if order is None or order["pw"] != pw:
            st.error("인증 실패")

        elif is_expired(order):
            show_expired_message()

        else:

            masked = " ".join(order["address"].split()[:3]) + " ***"

            st.success("조회 완료")

            st.write("### 주문 정보")

            st.write("**주문번호:**", oid)
            st.write("**수령인:**", order["buyer"])
            st.write("**주소:**", masked)

            if "product" in order:
                st.write("**구매 물품:**", order["product"])

            if "quantity" in order:
                st.write("**수량:**", f'{order["quantity"]}개')

            if "price" in order:
                st.write("**가격:**", f'{order["price"]:,}원')

            st.write("**상태:**", order["status"])

            remaining_time = get_remaining_time(order)

            if remaining_time:
                st.write(
                    "**남은 정보 공개시간:**",
                    remaining_time,
                )


            st.caption("※ 상세주소는 보안상 가려집니다.") 이코드의 실행화면 을 코랩에서 큐알로 찍어서 나오게 할려고 github를 쓸꺼야 단계별로 알려줘
