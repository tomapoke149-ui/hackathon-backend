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
    // ひとまず仮の空DBインスタンス（後ほどCloud SQLに接続させます）
    var db *sql.DB

    http.HandleFunc("/items", handler.GetItemsHandler(db))

    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }
    fmt.Printf("Server running on port %s...\n", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}
