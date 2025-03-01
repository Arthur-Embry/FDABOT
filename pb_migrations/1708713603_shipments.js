// shipments.js
migrate((app) => {
    let collection = new Collection({
        name: "shipments",
        type: "base",
        fields: [
            {
                name: "shipment_id",
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
                name: "product_type",
                type: "text",
                required: true
            },
            {
                name: "product_description",
                type: "text",
                required: true
            },
            {
                name: "hs_code",
                type: "text",
                required: false
            },
            {
                name: "quantity",
                type: "text",
                required: true
            },
            {
                name: "export_date",
                type: "date",
                required: true
            },
            {
                name: "departure_port",
                type: "text",
                required: true
            },
            {
                name: "arrival_port",
                type: "text",
                required: true
            },
            {
                name: "shipping_modality",
                type: "text",
                required: true
            },
            {
                name: "carrier",
                type: "text",
                required: false
            },
            {
                name: "compliance_status",
                type: "text",
                required: true
            }
        ]
    })
    return app.save(collection)
}, (app) => {
    let collection = app.findCollectionByNameOrId("shipments")
    return app.delete(collection)
})