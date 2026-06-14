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

func main() { // 👈 ここに { が必要です！
    mysqlUser := os.Getenv("MYSQL_USER")
    mysqlPwd := os.Getenv("MYSQL_PWD")
    mysqlHost := os.Getenv("MYSQL_HOST")
    mysqlDatabase := os.Getenv("MYSQL_DATABASE")

    connStr := fmt.Sprintf("%s:%s@%s/%s", mysqlUser, mysqlPwd, mysqlHost, mysqlDatabase)
    db, err := sql.Open("mysql", connStr)
    if err != nil {
        log.Fatal(err)
    }

    http.HandleFunc("/items", handler.GetItemsHandler(db))

    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }
    fmt.Printf("Server running on port %s...\n", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}