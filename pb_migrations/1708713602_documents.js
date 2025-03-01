// documents.js
migrate((app) => {
    let collection = new Collection({
        name: "documents",
        type: "base",
        fields: [
            {
                name: "document_id",
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
                name: "document_type",
                type: "text",
                required: true
            },
            {
                name: "format",
                type: "text",
                required: true
            },
            {
                name: "date_issued",
                type: "date",
                required: true
            },
            {
                name: "validity_period",
                type: "text",
                required: false
            },
            {
                name: "departure_port",
                type: "text",
                required: false
            },
            {
                name: "shipment_id",
                type: "text",
                required: false
            },
            {
                name: "status",
                type: "text",
                required: true
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
    let collection = app.findCollectionByNameOrId("documents")
    return app.delete(collection)
})