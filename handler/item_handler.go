package handler

import (
    "database/sql"
    "encoding/json"
    "net/http"
    "hackathon-backend/repository"
)

func GetItemsHandler(db *sql.DB) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        // CORSエラー回避のための設定（フロントエンドからの通信を許可）
        w.Header().Set("Access-Control-Allow-Origin", "*")
        w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
        
        if r.Method == "OPTIONS" {
            w.WriteHeader(http.StatusOK)
            return
        }

        items, err := repository.GetAllItems(db)
        if err != nil {
            http.Error(w, "Failed to fetch items: "+err.Error(), http.StatusInternalServerError)
            return
        }

        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(items)
    }
}
