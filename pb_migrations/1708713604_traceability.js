// traceability_records.js
migrate((app) => {
    let collection = new Collection({
        name: "traceability_records",
        type: "base",
        fields: [
            {
                name: "record_id",
                type: "text",
                required: true,
                unique: true
            },
            {
                name: "exporter_id",
                type: "text",
                required: true
            },
            {
                name: "food_product",
                type: "text",
                required: true
            },
            {
                name: "cte_type",
                type: "text",
                required: true
            },
            {
                name: "kde_details",
                type: "text",
                required: true
            },
            {
                name: "timestamp",
                type: "date",
                required: true
            },
            {
                name: "compliance_flag",
                type: "text",
                required: true
            },
            {
                name: "temperature",
                type: "number",
                required: false
            },
            {
                name: "humidity",
                type: "number",
                required: false
            },
            {
                name: "location_info",
                type: "text",
                required: false
            },
            {
                name: "lot_number",
                type: "text",
                required: false
            },
            {
                name: "batch_number",
                type: "text",
                required: false
            },
            {
                name: "supplier_id",
                type: "text",
                required: false
            },
            {
                name: "comments",
                type: "text",
                required: false
            }
        ]
    })
    return app.save(collection)
}, (app) => {
    let collection = app.findCollectionByNameOrId("traceability_records")
    return app.delete(collection)
})
