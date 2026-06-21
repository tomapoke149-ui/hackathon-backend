import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import main  # main.pyをインポート

client = TestClient(main.app)

# 💡 テスト実行中、データベースへの接続(get_db_connection)をすべてダミー（モック）に差し替える
@pytest.fixture(autouse=True)
def mock_db_connection():
    with patch("main.get_db_connection") as mock_connect:
        # ダミーのカーソルオブジェクトを作成
        mock_cursor = MagicMock()
        
        # /login や /recommend で使われる fetchone() や fetchall() のダミー戻り値を設定
        mock_cursor.fetchone.return_value = None  # ユーザーが存在しない状態を再現
        mock_cursor.fetchall.return_value = []    # 空のレコメンドリストを再現
        
        # get_db_connection() -> connection -> cursor() の流れをシミュレート
        mock_conn_obj = MagicMock()
        mock_conn_obj.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn_obj
        yield

def test_register_validation():
    """パスワードが6文字未満の時に正しく400エラーになるかテスト"""
    response = client.post(
        "/register",
        json={"email": "test_short@example.com", "password": "123"}
    )
    assert response.status_code == 400
    assert "パスワードは6文字以上" in response.json()["detail"]

def test_login_non_existent_user():
    """存在しないユーザーでログインしようとした時に444エラーになるかテスト"""
    response = client.post(
        "/login",
        json={"email": "notfound_user_999@example.com", "password": "password123"}
    )
    assert response.status_code == 444

def test_recommend_endpoint():
    """レコメンドエンドポイントが正常に200を返すかテスト"""
    response = client.get("/recommend?user_email=test@example.com")
    assert response.status_code == 200
    assert isinstance(response.json(), list)