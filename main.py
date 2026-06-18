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
    allow_credentials=False,
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

class ItemResponse(BaseModel):
    id: int
    name: str
    price: int
    is_sold: bool = False
    like_count: int = 0
    is_liked: bool = False
    user_email: str = ""
    description: Optional[str] = ""
    image_url: Optional[str] = ""

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
@app.post("/login")
def login(user: UserAuth):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # テーブルが存在しない場合は、アカウントが存在しない扱いにする
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
            
            if not db_user:
                raise HTTPException(status_code=444, detail="アカウントが見つかりません。新規登録してください。")
            
            # パスワードの一致確認
            if db_user["password"] != user.password:
                raise HTTPException(status_code=401, detail="パスワードが違います。")
                
        return {"status": "success", "message": "ログイン成功"}
    finally:
        connection.close()

@app.get("/get-items", response_model=List[ItemResponse])
def get_items(user_email: str = "", keyword: str = ""):
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
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
            try: cursor.execute("SELECT user_email FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN user_email VARCHAR(255) DEFAULT 'unknown@example.com'")
            
            try: cursor.execute("SELECT is_sold FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN is_sold BOOLEAN DEFAULT FALSE")

            try: cursor.execute("SELECT description FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN description TEXT")

            try: cursor.execute("SELECT image_url FROM items LIMIT 1")
            except Exception: cursor.execute("ALTER TABLE items ADD COLUMN image_url TEXT")

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

            sql_base = """
                SELECT i.id, i.name, i.price, COALESCE(i.is_sold, FALSE) as is_sold, i.user_email,
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
        connection.close()
        return result
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

@app.post("/buy-item")
def buy_item(id: int, user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
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
            
            cursor.execute("UPDATE items SET is_sold = TRUE WHERE id = %s", (id,))
            
            notif_msg = f"🎉 「{item['name']}」が {buyer_email} さんに購入されました！(+{item_price}pt)"
            cursor.execute("INSERT INTO notifications (user_email, message, item_id) VALUES (%s, %s, %s)", (seller_email, notif_msg, id))
            
            connection.commit()
        return {"status": "success"}
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
            cursor.execute("""
                SELECT i.id, i.name, i.price, COALESCE(i.is_sold, FALSE) as is_sold, i.user_email,
                       COALESCE(i.description, '') as description, COALESCE(i.image_url, '') as image_url,
                       COUNT(l.id) as like_count,
                       SUM(CASE WHEN l.user_email = %s THEN 1 ELSE 0 END) > 0 as is_liked
                FROM items i 
                LEFT JOIN likes l ON i.id = l.item_id
                WHERE i.is_sold = FALSE
                GROUP BY i.id 
                ORDER BY like_count DESC, i.id DESC 
                LIMIT 4
            """, (user_email,))
            
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

@app.get("/get-history", response_model=List[PointHistoryResponse])
def get_history(user_email: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
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
            connection.commit()

            cursor.execute("SELECT id, user_email, action_type, amount, item_name, created_at FROM point_history WHERE user_email = %s ORDER BY id DESC", (user_email,))
            result = cursor.fetchall()
            for row in result:
                if row.get("created_at"):
                    row["created_at"] = row["created_at"].strftime("%m/%d %H:%M")
            return result
    finally:
        connection.close()