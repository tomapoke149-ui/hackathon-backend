import os
import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 💡 認証用のデータ型を定義
class UserAuth(BaseModel):
    email: str
    password: str

class Item(BaseModel):
    name: str 
    price: int
    user_email: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""

# 💡 ファイルの上のほうにある ItemResponse を以下のように上書きします
class ItemResponse(BaseModel):
    id: int
    name: str
    price: int
    is_sold: bool
    user_email: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    like_count: Optional[int] = 0
    is_liked: Optional[bool] = False
    # ⭐ ここを新しく追加！省略可能（Optional）にしておきます
    buyer_email: Optional[str] = None
    trade_status: Optional[str] = "available"
    is_shipped: Optional[bool] = False
    is_completed: Optional[bool] = False

class NotificationResponse(BaseModel):
    id: int
    message: str
    item_id: Optional[int] = None
    is_read: bool = False

class CommentCreate(BaseModel):
    item_id: int
    user_email: str
    content: str

class CommentResponse(BaseModel):
    id: int
    item_id: int
    user_email: str
    content: str
    created_at: Optional[str] = None

class DMCreate(BaseModel):
    receiver_email: str
    message: str
    
class DMResponse(BaseModel):
    id: int
    sender_email: str
    receiver_email: str
    message: str
    created_at: Optional[str] = None

class PointHistoryResponse(BaseModel):
    id: int
    user_email: str
    action_type: str
    amount: int
    item_name: Optional[str] = ""
    created_at: Optional[str] = None
    
def get_db_connection():
    db_user = os.getenv("MYSQL_USER")
    db_pwd = os.getenv("MYSQL_PWD")
    db_host_port = os.getenv("MYSQL_HOST", "")
    db_name = os.getenv("MYSQL_DATABASE")

    if ":" in db_host_port:
        host, port_str = db_host_port.split(":")
        port = int(port_str)
    else:
        host = db_host_port
        port = 3306

    return pymysql.connect(
        host=host,
        port=port,
        user=db_user,
        password=db_pwd,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"fake_user": True}
    )

# 💡 新規追加：本物の「ユーザー登録」API（重複エラーをチェック！）
# 💡 新規追加：本物の「ユーザー登録」API（安全なエラー処理版）
@app.post("/register")
def register(user: UserAuth):
    if not user.password or len(user.password) < 6:
        raise HTTPException(status_code=400, detail="パスワードは6文字以上で設定してください。")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 💡 もしすでにname列が存在するusersテーブルがあっても壊れないように、
            # 最初からname列をNULL許可(またはデフォルト空文字)にするように作成・修正を試みる
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email VARCHAR(255) PRIMARY KEY,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(255) DEFAULT ''
                )
            """)
            try:
                cursor.execute("SELECT name FROM users LIMIT 1")
            except Exception:
                cursor.execute("ALTER TABLE users ADD COLUMN name VARCHAR(255) DEFAULT ''")
            connection.commit()

            # 重複チェック
            cursor.execute("SELECT email FROM users WHERE email = %s", (user.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="このメールアドレスは既に登録されています。ログインしてください。")

            # 💡 エラー対策：INSERT文で、念のため 'name' 列にも空文字を入れるように指定する
            cursor.execute(
                "INSERT INTO users (email, password, name) VALUES (%s, %s, '')", 
                (user.email, user.password)
            )
            
            # 初期ポイントのセットアップ
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_wallets (
                    user_email VARCHAR(255) PRIMARY KEY,
                    points INT DEFAULT 10000
                )
            """)
            cursor.execute("INSERT INTO user_wallets (user_email, points) VALUES (%s, 10000) ON DUPLICATE KEY UPDATE points=points", (user.email,))
            
            connection.commit()
        return {"status": "success", "message": "ユーザー登録が完了しました"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ 登録エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()
# 💡 新規追加：本物の「ログイン」API（パスワード違いをしっかり弾く！）
# 💡 修正版：アカウントがなければその場で自動登録する「ログイン＆自動同期」API
@app.post("/login")
def login(user: UserAuth):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # テーブルが存在しない場合は作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email VARCHAR(255) PRIMARY KEY,
                    password VARCHAR(255) NOT NULL
                )
            """)
            connection.commit()

            # ユーザー検索
            cursor.execute("SELECT password FROM users WHERE email = %s", (user.email,))
            db_user = cursor.fetchone()
            
            # ① GCPで認証済みだけどMySQLにまだいない場合は、自動で登録（初期同期）
            if not db_user:
                # 念のため、上の新規登録処理と同じように、name列がある場合は空文字をいれるか、なければemailやpasswordだけで登録します
                cursor.execute(
                    "INSERT INTO users (email, password) VALUES (%s, %s)",
                    (user.email, user.password)
                )
                
                # 初期ポイント（ウォレット）も自動で作ってあげる（親切設計）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_wallets (
                        user_email VARCHAR(255) PRIMARY KEY,
                        points INT DEFAULT 10000
                    )
                """)
                cursor.execute("INSERT INTO user_wallets (user_email, points) VALUES (%s, 10000) ON DUPLICATE KEY UPDATE points=points", (user.email,))
                
                connection.commit()
                return {"status": "success", "message": "新規ユーザー登録＆同期成功"}
            
            # ② 🔄 もしGCPのパスワードとMySQLのパスワードが違ったら、最新に更新する（再設定対策）
            if db_user["password"] != user.password:
                cursor.execute(
                    "UPDATE users SET password = %s WHERE email = %s",
                    (user.password, user.email)
                )
                connection.commit()
                return {"status": "success", "message": "パスワード同期＆ログイン成功"}
                
        return {"status": "success", "message": "ログイン成功"}
        
    except Exception as e:
        print(f"❌ ログイン/同期エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 💡 ここが漏れていたため、しっかりとクローズを追加して閉じます！
        connection.close()
@app.get("/get-items", response_model=List[ItemResponse])
def get_items(user_email: str = "", keyword: str = ""):
    try:
        connection = get_db_connection()
        
        with connection.cursor() as cursor:
            # 1. 各種テーブルの作成（未作成の場合のみ）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    price INT NOT NULL,
                    is_sold BOOLEAN DEFAULT FALSE,
                    user_email VARCHAR(255) DEFAULT 'unknown@example.com',
                    description TEXT,
                    image_url TEXT
                )
            """)
            
            # 💡 カラムの追加チェック（エラー防止対策）
            try: cursor.execute("SELECT user_email FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN user_email VARCHAR(255) DEFAULT 'unknown@example.com'")
            
            try: cursor.execute("SELECT is_sold FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN is_sold BOOLEAN DEFAULT FALSE")

            try: cursor.execute("SELECT description FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN description TEXT")

            try: cursor.execute("SELECT image_url FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN image_url TEXT")

            # ⭐ 追加：今回の取引に必要なカラムがDBになければ自動追加する
            try: cursor.execute("SELECT buyer_email FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN buyer_email VARCHAR(255) DEFAULT NULL")

            try: cursor.execute("SELECT trade_status FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN trade_status VARCHAR(50) DEFAULT 'available'")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS likes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    item_id INT NOT NULL,
                    user_email VARCHAR(255) NOT NULL,
                    UNIQUE KEY unique_user_item (item_id, user_email)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_email VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    item_id INT DEFAULT NULL,
                    is_read BOOLEAN DEFAULT FALSE
                )
            """)
            try: cursor.execute("SELECT item_id FROM notifications LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE notifications ADD COLUMN item_id INT DEFAULT NULL")
            try: cursor.execute("SELECT is_read FROM notifications LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE notifications ADD COLUMN is_read BOOLEAN DEFAULT FALSE")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    item_id INT NOT NULL,
                    user_email VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            connection.commit()

            # 2. 💡 正しい順番：まずSQLでいいね数や商品データを結合して取得する
            # (SELECT項目に buyer_email と trade_status もしっかり追加しています)
            sql_base = """
                SELECT i.id, i.name, i.price, COALESCE(i.is_sold, FALSE) as is_sold, i.user_email,
                       COALESCE(i.buyer_email, '') as buyer_email, COALESCE(i.trade_status, 'available') as trade_status,
                       COALESCE(i.description, '') as description, COALESCE(i.image_url, '') as image_url,
                       COUNT(l.id) as like_count,
                       SUM(CASE WHEN l.user_email = %s THEN 1 ELSE 0 END) > 0 as is_liked
                FROM items i LEFT JOIN likes l ON i.id = l.item_id
            """
            if keyword:
                cursor.execute(sql_base + " WHERE i.name LIKE %s GROUP BY i.id ORDER BY i.id DESC", (user_email, f"%{keyword}%"))
            else:
                cursor.execute(sql_base + " GROUP BY i.id ORDER BY i.id DESC", (user_email,))
            
            result = cursor.fetchall()

            # 3. 取得したデータに対して、React用のフラグを完璧に仕込む
            items_data = []
            for row in result:
                item = dict(row)
                
                status = item.get("trade_status") or "available"
                
                # React側でボタンや履歴の表示判定に使うフラグを明示的にセット
                item["is_shipped"] = (status in ['shipped', 'completed'])
                item["is_completed"] = (status == 'completed')
                
                # is_sold も trade_status に合わせて一応 true/false にしておく
                item["is_sold"] = (status != "available")
                
                # 💡 None や未定義の項目があれば、エラーにならないよう初期値を仕込む
                if "like_count" not in item or item["like_count"] is None:
                    item["like_count"] = 0
                if "is_liked" not in item:
                    item["is_liked"] = False
                
                items_data.append(item)

        connection.close()
        return items_data  # これで ItemResponse の型と1ミリのズレもなくなり、エラーが消滅します！
    except Exception as e:
        print(f"データ取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"データ取得エラー: {e}")

@app.post("/items", status_code=201)
def create_item(item: Item):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO items (name, price, user_email, description, image_url) VALUES (%s, %s, %s, %s, %s)", 
                (item.name, item.price, item.user_email, item.description, item.image_url)
            )
            connection.commit()
        return {"message": "success"}
    finally:
        connection.close()

@app.delete("/delete-item")
def delete_item(id: int, user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_email FROM items WHERE id = %s", (id,))
            item = cursor.fetchone()
            if not item or item["user_email"] != user_email:
                raise HTTPException(status_code=403, detail="削除不可")
            cursor.execute("DELETE FROM items WHERE id = %s", (id,))
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

@app.post("/post-comment")
def post_comment(comment: CommentCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO comments (item_id, user_email, content) VALUES (%s, %s, %s)", (comment.item_id, comment.user_email, comment.content))
            
            cursor.execute("SELECT name, user_email FROM items WHERE id = %s", (comment.item_id,))
            item = cursor.fetchone()
            if item and item["user_email"] != comment.user_email:
                notif_msg = f"💬 {comment.user_email} さんが「{item['name']}」にコメントしました"
                cursor.execute("SELECT id FROM notifications WHERE user_email = %s AND message = %s", (item["user_email"], notif_msg))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO notifications (user_email, message, item_id) VALUES (%s, %s, %s)", (item["user_email"], notif_msg, comment.item_id))
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

@app.get("/get-comments", response_model=List[CommentResponse])
def get_comments(item_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, item_id, user_email, content, created_at FROM comments WHERE item_id = %s ORDER BY id ASC", (item_id,))
            result = cursor.fetchall()
            for row in result:
                if row.get("created_at"):
                    row["created_at"] = str(row["created_at"])
            return result
    except Exception as e:
        print(f"❌ コメント取得で重大なエラーが発生: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.delete("/delete-comment")
def delete_comment(comment_id: int, user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT c.user_email as commenter, i.user_email as owner FROM comments c JOIN items i ON c.item_id = i.id WHERE c.id = %s", (comment_id,))
            info = cursor.fetchone()
            if not info or (user_email != info["commenter"] and user_email != info["owner"]):
                raise HTTPException(status_code=403, detail="権限なし")
            cursor.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

@app.post("/like-item")
def like_item(item_id: int, user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM likes WHERE item_id = %s AND user_email = %s", (item_id, user_email))
            like = cursor.fetchone()
            cursor.execute("SELECT name, user_email as owner FROM items WHERE id = %s", (item_id,))
            item = cursor.fetchone()
            item_name = item["name"] if item else "不明な商品"
            owner_email = item["owner"] if item else ""

            if like:
                cursor.execute("DELETE FROM likes WHERE item_id = %s AND user_email = %s", (item_id, user_email))
            else:
                cursor.execute("INSERT INTO likes (item_id, user_email) VALUES (%s, %s)", (item_id, user_email))
                if owner_email and owner_email != user_email:
                    notif_msg = f"💌 「{item_name}」が {user_email} さんにいいね！されました"
                    cursor.execute("SELECT id FROM notifications WHERE user_email = %s AND message = %s", (owner_email, notif_msg))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO notifications (user_email, message, item_id) VALUES (%s, %s, %s)", (owner_email, notif_msg, item_id))
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

@app.get("/notifications", response_model=List[NotificationResponse])
def get_notifications(user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, message, item_id, COALESCE(is_read, FALSE) as is_read FROM notifications WHERE user_email = %s ORDER BY id DESC LIMIT 20", (user_email,))
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/notifications/read")
def mark_notifications_read(user_email: str = ""):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE notifications SET is_read = TRUE WHERE user_email = %s AND is_read = FALSE", (user_email,))
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

# 💡 1. フロントからJSON形式でデータが送られてきた時用の型定義を定義（関数のすぐ上に書くと安全です）
class BuyItemRequest(BaseModel):
    id: int
    user_email: str


from fastapi import FastAPI, HTTPException, Query  # 💡 一番上に「Query」をインポートします（すでにあれば不要）

# 💡 ここから置き換え
@app.post("/buy-item")
def buy_item(id: int = Query(...), user_email: str = Query(...)):  # 💡 = Query(...) を追加して、URLパラメータからの受け取りを強制します
    if not id or not user_email:
        raise HTTPException(status_code=400, detail="商品IDまたはユーザーメールアドレスが不足しています")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 💡 ここから下のデータベース処理（元々これね、と書いてくださった部分）は、今のままで一切変更しなくて大丈夫です！
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS point_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_email VARCHAR(255) NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    amount INT NOT NULL,
                    item_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("SELECT name, price, user_email as owner_email, is_sold FROM items WHERE id = %s", (id,))
            item = cursor.fetchone()
            
            if not item:
                raise HTTPException(status_code=444, detail="商品が見つかりません")
            if item["is_sold"]:
                raise HTTPException(status_code=400, detail="この商品は売り切れです")
            if item["owner_email"] == user_email:
                raise HTTPException(status_code=400, detail="自分の商品は購入できません")

            buyer_email = user_email
            seller_email = item["owner_email"]
            item_price = item["price"]

            cursor.execute("SELECT points FROM user_wallets WHERE user_email = %s", (buyer_email,))
            buyer_wallet = cursor.fetchone()
            buyer_points = buyer_wallet["points"] if buyer_wallet else 10000
            
            if buyer_points < item_price:
                raise HTTPException(status_code=400, detail="アプリ内通貨（ポイント）が足りません！")

            cursor.execute("UPDATE user_wallets SET points = points - %s WHERE user_email = %s", (item_price, buyer_email))
            
            cursor.execute(
                "INSERT INTO point_history (user_email, action_type, amount, item_name) VALUES (%s, 'buy', %s, %s)",
                (buyer_email, -item_price, item["name"])
            )
            
            cursor.execute("""
                INSERT INTO user_wallets (user_email, points) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE points = points + %s
            """, (seller_email, item_price, item_price))
            
            cursor.execute(
                "INSERT INTO point_history (user_email, action_type, amount, item_name) VALUES (%s, 'sell', %s, %s)",
                (seller_email, item_price, item["name"])
            )
            
            # 🌟 購入者情報と取引ステータスを確実に保存
            cursor.execute("""
                UPDATE items 
                SET is_sold = TRUE, buyer_email = %s, trade_status = 'trading' 
                WHERE id = %s
            """, (buyer_email, id))
            
            notif_msg = f"🎉 「{item['name']}」が {buyer_email} さんに購入されました！(+{item_price}pt)"
            cursor.execute("INSERT INTO notifications (user_email, message, item_id) VALUES (%s, %s, %s)", (seller_email, notif_msg, id))
            
            connection.commit()
        return {"status": "success", "message": "購入が成功しました！"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ 購入重大エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()
        
@app.get("/get-points")
def get_points(user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_wallets (
                    user_email VARCHAR(255) PRIMARY KEY,
                    points INT DEFAULT 10000
                )
            """)
            connection.commit()

            cursor.execute("SELECT points FROM user_wallets WHERE user_email = %s", (user_email,))
            wallet = cursor.fetchone()
            if not wallet:
                cursor.execute("INSERT INTO user_wallets (user_email, points) VALUES (%s, 10000)", (user_email,))
                connection.commit()
                return {"points": 10000}
            return {"points": wallet["points"]}
    finally:
        connection.close()      

@app.get("/recommend", response_model=List[ItemResponse])
def get_recommendations(item_id: Optional[int] = None, user_email: str = ""):
    """
    KaggleのeCommerce行動データやフリマの性質を踏まえたレコメンドエンドポイント。
    特定のベース商品(item_id)がある場合は、その商品の価格帯や名前の類似度（簡易カテゴリー）から推薦。
    ない場合は、まだ売り切れていない人気商品や新着商品を推薦します。
    """
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 特定の商品をベースに推薦する場合
            if item_id:
                # ベースとなる商品の情報を取得
                cursor.execute("SELECT name, price FROM items WHERE id = %s", (item_id,))
                base_item = cursor.fetchone()
                
                if base_item:
                    # 価格帯が近く、売り切れていない、かつ自分自身ではない商品を最大4件取得 (協調フィルタリングやコンテンツベースの簡易版)
                    cursor.execute("""
                        SELECT i.id, i.name, i.price, COALESCE(i.is_sold, FALSE) as is_sold, i.user_email,
                               COALESCE(i.description, '') as description, COALESCE(i.image_url, '') as image_url,
                               COUNT(l.id) as like_count,
                               SUM(CASE WHEN l.user_email = %s THEN 1 ELSE 0 END) > 0 as is_liked
                        FROM items i 
                        LEFT JOIN likes l ON i.id = l.item_id
                        WHERE i.id != %s AND i.is_sold = FALSE 
                          AND i.price BETWEEN %s AND %s
                        GROUP BY i.id 
                        ORDER BY like_count DESC, i.id DESC 
                        LIMIT 4
                    """, (user_email, item_id, int(base_item["price"] * 0.5), int(base_item["price"] * 1.5)))
                    
                    recommendations = cursor.fetchall()
                    if recommendations:
                        return recommendations
# 2. ベース商品がない、または類似商品が見つからない場合は「新着・人気商品」をレコメンド
            # (いいねが0件でも確実に商品を出すためにSQLをシンプルにします)
            cursor.execute("""
                SELECT id, name, price, COALESCE(is_sold, FALSE) as is_sold, user_email,
                       COALESCE(description, '') as description, COALESCE(image_url, '') as image_url
                FROM items 
                WHERE is_sold = FALSE
                ORDER BY id DESC 
                LIMIT 4
            """)
            
            recommendations = cursor.fetchall()
            # フロントエンドの型エラーを防ぐために、足りないプロパティを補う
            for r in recommendations:
                r["like_count"] = 0
                r["is_liked"] = False
                
            return recommendations
            
            return cursor.fetchall()
    except Exception as e:
        print(f"❌ レコメンドエラー: {e}")
        raise HTTPException(status_code=500, detail="レコメンドデータの取得に失敗しました")
    finally:
        connection.close()

@app.post("/send-dm")
def send_dm(dm: DMCreate, sender_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dm_messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sender_email VARCHAR(255) NOT NULL,
                    receiver_email VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute(
                "INSERT INTO dm_messages (sender_email, receiver_email, message) VALUES (%s, %s, %s)",
                (sender_email, dm.receiver_email, dm.message)
            )
            
            notif_msg = f"📩 {sender_email} さんから新着DM: {dm.message[:15]}..."
            cursor.execute(
                "INSERT INTO notifications (user_email, message, is_read) VALUES (%s, %s, FALSE)",
                (dm.receiver_email, notif_msg)
            )
            
            connection.commit()
        return {"status": "success"}
    finally:
        connection.close()

@app.get("/get-dms", response_model=List[DMResponse])
def get_dms(user_email: str, other_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dm_messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sender_email VARCHAR(255) NOT NULL,
                    receiver_email VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.commit()

            cursor.execute("""
                SELECT id, sender_email, receiver_email, message, created_at 
                FROM dm_messages 
                WHERE (sender_email = %s AND receiver_email = %s)
                   OR (sender_email = %s AND receiver_email = %s)
                ORDER BY id ASC
            """, (user_email, other_email, other_email, user_email))
            
            result = cursor.fetchall()
            
            for row in result:
                if row.get("created_at"):
                    try:
                        row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        row["created_at"] = str(row["created_at"])
                else:
                    row["created_at"] = ""
            return result
    except Exception as e:
        print(f"❌ DM取得でエラー発生: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

        # ==========================================
## ==========================================
# 💡 ここから下を main.py の一番最後に追記（上書き）
# ==========================================

class FollowAction(BaseModel):
    follower_email: str
    followee_email: str

class ProfileUpdate(BaseModel):
    email: str
    bio: str



# ==========================================
## ==========================================
# 💡 main.py の一番最後に追記（上書き）する完成版コード
# ==========================================

from pydantic import BaseModel
from typing import Optional, List  # ← インポート漏れ防止

class FollowAction(BaseModel):
    follower_email: str
    followee_email: str

class ProfileUpdate(BaseModel):
    email: str
    bio: str

class TransactionAction(BaseModel):
    item_id: int
    user_email: str
    rating: Optional[int] = None    # 発送時は送られてこないので省略可能にする
    comment: Optional[str] = None   # 省略可能にする



# 💡 3. APIエンドポイント（関数）の定義
@app.get("/get-trade-history")
def get_trade_history(user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 💡 【超重要】buyer_emailの厳しい縛りを完全に消去！
            # 自分が「出品者」または「購入者」であり、かつ「売り切れ(is_sold=1/True)」または「取引中」なら全件強制取得
            cursor.execute("""
                SELECT id, name, price, user_email, buyer_email, trade_status, created_at 
                FROM items 
                WHERE (user_email = %s OR buyer_email = %s)
                  AND (is_sold = 1 OR is_sold IS TRUE OR COALESCE(trade_status, 'available') != 'available')
                ORDER BY id DESC
            """, (user_email, user_email))
            
            result = cursor.fetchall()
            trade_data = []
            
            for row in result:
                item = dict(row)
                
                # 日時の変換
                if item.get("created_at") and not isinstance(item["created_at"], str):
                    item["created_at"] = item["created_at"].strftime("%m/%d %H:%M")
                else:
                    item["created_at"] = str(item.get("created_at") or "")
                
                # trade_status の文字列を見て、React用のフラグを安全に判定
                status = item.get("trade_status") or "available"
                item["is_shipped"] = (status in ['shipped', 'completed'])
                item["is_completed"] = (status == 'completed')
                
                # 💡 buyer_email が空だった場合にフロントがクラッシュするのを防ぐダミー補完
                if not item.get("buyer_email"):
                    item["buyer_email"] = "unknown_buyer@example.com"
                
                trade_data.append(item)

            return trade_data
    except Exception as e:
        print(f"❌ 履歴取得エラー: {e}")
        return []
    finally:
        connection.close()
@app.get("/user-profile")
def get_user_profile(target_email: str, current_user_email: str = ""):
    """プロフィール取得（自己紹介や評価も取得）"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 必要なテーブルを追加作成（自己紹介用、評価用）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    email VARCHAR(255) PRIMARY KEY,
                    bio TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    item_id INT,
                    target_email VARCHAR(255),
                    reviewer_email VARCHAR(255),
                    rating INT,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 商品テーブルに取引ステータスと購入者用のカラムを追加
            try:
                cursor.execute("ALTER TABLE items ADD COLUMN trade_status VARCHAR(50) DEFAULT 'available'")
                cursor.execute("ALTER TABLE items ADD COLUMN buyer_email VARCHAR(255)")
            except:
                pass # すでにカラムがある場合は無視

            connection.commit()

            # 自己紹介を取得
            cursor.execute("SELECT bio FROM user_profiles WHERE email = %s", (target_email,))
            profile_row = cursor.fetchone()
            bio = profile_row["bio"] if profile_row else ""

            # 評価（平均星とレビュー一覧）を取得
            cursor.execute("SELECT AVG(rating) as avg_rating, COUNT(*) as review_count FROM reviews WHERE target_email = %s", (target_email,))
            rating_data = cursor.fetchone()
            
            cursor.execute("SELECT reviewer_email, rating, comment, created_at FROM reviews WHERE target_email = %s ORDER BY id DESC", (target_email,))
            reviews = cursor.fetchall()

            # フォロワー数、フォロー数を取得
            cursor.execute("SELECT COUNT(*) as follower_count FROM follows WHERE followee_email = %s", (target_email,))
            follower_count = cursor.fetchone()["follower_count"]

            cursor.execute("SELECT COUNT(*) as following_count FROM follows WHERE follower_email = %s", (target_email,))
            following_count = cursor.fetchone()["following_count"]

            is_following = False
            if current_user_email:
                cursor.execute("SELECT id FROM follows WHERE follower_email = %s AND followee_email = %s", (current_user_email, target_email))
                if cursor.fetchone():
                    is_following = True

            # 出品商品を取得（取引ステータスも）
            cursor.execute("""
                SELECT i.id, i.name, i.price, COALESCE(i.is_sold, FALSE) as is_sold, i.user_email,
                       COALESCE(i.description, '') as description, COALESCE(i.image_url, '') as image_url,
                       COALESCE(i.trade_status, 'available') as trade_status, COALESCE(i.buyer_email, '') as buyer_email,
                       COUNT(l.id) as like_count
                FROM items i 
                LEFT JOIN likes l ON i.id = l.item_id
                WHERE i.user_email = %s
                GROUP BY i.id 
                ORDER BY i.id DESC
            """, (target_email,))
            items = cursor.fetchall()

            return {
                "email": target_email,
                "bio": bio,
                "follower_count": follower_count,
                "following_count": following_count,
                "is_following": is_following,
                "avg_rating": float(rating_data["avg_rating"] or 0),
                "review_count": rating_data["review_count"],
                "reviews": reviews,
                "items": items
            }
    finally:
        connection.close()

from fastapi import FastAPI, HTTPException, Query, Request, Body

@app.post("/toggle-follow")
async def toggle_follow(
    request: Request,
    user_email: Optional[str] = Query(None),
    target_email: Optional[str] = Query(None),
    follower_email: Optional[str] = Query(None),
    followee_email: Optional[str] = Query(None)
):
    """どんな形式（JSON/URLパラメータ）やキー名で送られてきても、絶対にデータを救出して処理する防弾API"""
    
    # 1. まずURLのクエリパラメータからデータを救出
    u_email = user_email or follower_email
    t_email = target_email or followee_email

    # 2. もしクエリパラメータになければ、JSONボディからデータを救出
    if not u_email or not t_email:
        try:
            body = await request.json()
            if body:
                u_email = body.get("user_email") or body.get("follower_email")
                t_email = body.get("target_email") or body.get("followee_email") or body.get("followee")
        except Exception:
            pass

    # それでもデータが取れなかったらエラー
    if not u_email or not t_email:
        raise HTTPException(
            status_code=400, 
            detail=f"フォロー情報が不足しています (取得値 -> follower:{u_email}, followee:{t_email})"
        )

    if u_email == t_email:
        raise HTTPException(status_code=400, detail="自分自身をフォローすることはできません")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # テーブルが存在することを確認
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    follower_email VARCHAR(255) NOT NULL,
                    followee_email VARCHAR(255) NOT NULL,
                    UNIQUE KEY unique_follow (follower_email, followee_email)
                )
            """)
            connection.commit()

            # すでにフォローしているかチェック
            cursor.execute(
                "SELECT id FROM follows WHERE follower_email = %s AND followee_email = %s", 
                (u_email, t_email)
            )
            follow = cursor.fetchone()

            if follow:
                cursor.execute("DELETE FROM follows WHERE id = %s", (follow["id"],))
                status = "unfollowed"
            else:
                cursor.execute(
                    "INSERT INTO follows (follower_email, followee_email) VALUES (%s, %s)", 
                    (u_email, t_email)
                )
                status = "followed"
                
                # 通知送信
                notif_msg = f"✨ {u_email.split('@')[0]} さんにフォローされました！"
                try:
                    cursor.execute("SELECT id FROM notifications WHERE user_email = %s AND message = %s AND created_at > NOW() - INTERVAL 1 DAY", (t_email, notif_msg))
                    has_notif = cursor.fetchone()
                except Exception:
                    cursor.execute("SELECT id FROM notifications WHERE user_email = %s AND message = %s", (t_email, notif_msg))
                    has_notif = cursor.fetchone()

                if not has_notif:
                    cursor.execute("INSERT INTO notifications (user_email, message, is_read) VALUES (%s, %s, FALSE)", (t_email, notif_msg))

            connection.commit()
            return {"status": "success", "action": status, "message": "フォロー状態を更新しました"}
    except Exception as e:
        print(f"❌ フォロー重大エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.post("/update-bio")
def update_bio(profile: ProfileUpdate):
    """自己紹介の更新"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_profiles (email, bio) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE bio = %s
            """, (profile.email, profile.bio, profile.bio))
            connection.commit()
            return {"status": "success"}
    finally:
        connection.close()

@app.get("/get-follow-stats")
def get_follow_stats(user_email: str, login_user_email: str = ""):
    """フォロー・フォロワーの具体的なメールアドレスのリスト（配列）を返すAPI"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    follower_email VARCHAR(255) NOT NULL,
                    followee_email VARCHAR(255) NOT NULL
                )
            """)
            connection.commit()
            
            # その人がフォローしている人（followee_email）のリスト
            cursor.execute("SELECT followee_email FROM follows WHERE follower_email = %s", (user_email,))
            following_list = [r["followee_email"] for r in cursor.fetchall()]
            
            # その人をフォローしている人（follower_email）のリスト
            cursor.execute("SELECT follower_email FROM follows WHERE followee_email = %s", (user_email,))
            follower_list = [r["follower_email"] for r in cursor.fetchall()]
            
            # ログインユーザーが、このプロフィール主をフォローしているかどうか
            is_following = False
            if login_user_email:
                cursor.execute("SELECT id FROM follows WHERE follower_email = %s AND followee_email = %s", (login_user_email, user_email))
                is_following = cursor.fetchone() is not None
                
            return {
                "following_count": len(following_list),
                "follower_count": len(follower_list),
                "following": following_list,
                "followers": follower_list,
                "is_following": is_following
            }
    finally:
        connection.close()

@app.post("/ship-item")
def ship_item(action: TransactionAction):
    """出品者が発送ボタンを押したときの処理"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # ステータスをshipped（発送済み）に更新
            cursor.execute("UPDATE items SET trade_status = 'shipped' WHERE id = %s AND user_email = %s", (action.item_id, action.user_email))
            
            # 購入者へ通知
            cursor.execute("SELECT name, buyer_email FROM items WHERE id = %s", (action.item_id,))
            item = cursor.fetchone()
            if item and item["buyer_email"]:
                msg = f"📦 {action.user_email} さんが「{item['name']}」を発送しました！到着をお待ちください。"
                cursor.execute("INSERT INTO notifications (user_email, message, is_read) VALUES (%s, %s, FALSE)", (item["buyer_email"], msg))
            
            connection.commit()
            return {"status": "success"}
    finally:
        connection.close()

@app.post("/complete-transaction")
def complete_transaction(action: TransactionAction):
    """購入者が受取評価をして取引を完了する処理"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 商品情報を取得して出品者を特定
            cursor.execute("SELECT user_email, name FROM items WHERE id = %s", (action.item_id,))
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            seller_email = item["user_email"]

            # ステータスをcompleted（取引完了）に更新
            cursor.execute("UPDATE items SET trade_status = 'completed' WHERE id = %s", (action.item_id,))
            
            # 評価を保存
            cursor.execute("""
                INSERT INTO reviews (item_id, target_email, reviewer_email, rating, comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (action.item_id, seller_email, action.user_email, action.rating, action.comment))

            # 出品者へ通知
            msg = f"🎉 {action.user_email} さんが「{item['name']}」の受取評価（★{action.rating}）をして取引が完了しました！"
            cursor.execute("INSERT INTO notifications (user_email, message, is_read) VALUES (%s, %s, FALSE)", (seller_email, msg))

            connection.commit()
            return {"status": "success"}
    finally:
        connection.close()