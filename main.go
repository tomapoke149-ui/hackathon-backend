package main

import (
    "database/sql"
    "fmt"
    "log"
    "net/http"
    "os"
    "hackathon-backend/handler"
    _ "github.com/go-sql-driver/mysql"
)

func main() {
    mysqlUser := os.Getenv("MYSQL_USER")
    mysqlPwd := os.Getenv("MYSQL_PWD")
    mysqlHost := os.Getenv("MYSQL_HOST")
    mysqlDatabase := os.Getenv("MYSQL_DATABASE")

    connStr := fmt.Sprintf("%s:%s@%s/%s", mysqlUser, mysqlPwd, mysqlHost, mysqlDatabase)
    db, err := sql.Open("mysql", connStr)
    if err != nil {
        log.Fatal(err)
    }

    // 👇 ここを追加！トップページ (/) にアクセスが来たときのお返事
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintln(w, "Hello Hackathon Backend!")
    })

    // 既存の /items の処理
    http.HandleFunc("/items", handler.GetItemsHandler(db))

    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }
    fmt.Printf("Server running on port %s...\n", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}