package repository

import (
    "database/sql"
    "hackathon-backend/model"
)

func GetAllItems(db *sql.DB) ([]model.Item, error) {
    rows, err := db.Query("SELECT id, title, description, price FROM items")
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var items []model.Item
    for rows.Next() {
        var item model.Item
        if err := rows.Scan(&item.ID, &item.Title, &item.Description, &item.Price); err != nil {
            return nil, err
        }
        items = append(items, item)
    }
    return items, nil
}
