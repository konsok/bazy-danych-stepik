const express = require("express");
const productRoutes = express.Router();
const dbo = require("../db/conn");
const ObjectId = require("mongodb").ObjectId;

// zwraca wszystkie produkty z mozliwoscia filtrowania i sortowania
productRoutes.route("/products").get(function (req, res) {
  let db_connect = dbo.getDb("store");

  const filter = {};
  if (req.query.name) filter.name = req.query.name;
  if (req.query.price) filter.price = req.query.price;
  if (req.query.description) filter.description = req.query.description;
  if (req.query.quantity) filter.quantity = req.query.quantity;

  const sort = {};
  if (req.query.sortBy === "name")
    sort.name = req.query.sortOrder === "asc" ? 1 : -1;
  if (req.query.sortBy === "price")
    sort.price = req.query.sortOrder === "asc" ? 1 : -1;
  if (req.query.sortBy === "description")
    sort.description = req.query.sortOrder === "asc" ? 1 : -1;
  if (req.query.sortBy === "quantity")
    sort.quantity = req.query.sortOrder === "asc" ? 1 : -1;

  db_connect
    .collection("products")
    .find(filter)
    .sort(sort)
    .toArray((err, products) => {
      if (err) res.status(500).send(err);
      else res.send(products);
    });
});

// zwraca produkt o podanym id

productRoutes.route("/products/:id").get(function (req, res) {
  let db_connect = dbo.getDb("store");
  let myquery = { _id: ObjectId(req.params.id) };
  db_connect.collection("products").findOne(myquery, function (err, result) {
    if (err) throw err;
    res.json(result);
  });
});

// dodaje nowy produkt do bazy oraz sprawdza czy nazwa produktu jest unikalna

productRoutes.route("/products/add").post(function (req, res) {
  let db_connect = dbo.getDb("store");
  let myobj = {
    name: req.body.name,
    price: req.body.price,
    description: req.body.description,
    quantity: req.body.quantity,
  };

  db_connect
    .collection("products")
    .findOne({ name: myobj.name }, (err, result) => {
      if (err) throw err;
      if (!result) {
        db_connect.collection("products").insertOne(myobj, (err, result) => {
          if (err) throw err;
          res.json(result);
        });
      } else {
        res.status(400).send("Product name is not unique");
      }
    });
});

// aktualizuje produkt o podanym id

productRoutes.route("/update/:id").put(function (req, res) {
  let db_connect = dbo.getDb("store");
  let myquery = { _id: ObjectId(req.params.id) };
  let newvalues = {
    $set: {
      name: req.body.name,
      price: req.body.price,
      description: req.body.description,
      quantity: req.body.quantity,
    },
  };
  db_connect
    .collection("products")
    .updateOne(myquery, newvalues, function (err, result) {
      if (err) throw err;
      console.log("1 document updated");
      res.json(result);
    });
});

// usuwa produkt o podanym id

productRoutes.route("/delete/:id").delete(function (req, res) {
  let db_connect = dbo.getDb("store");
  let myquery = { _id: ObjectId(req.params.id) };
  db_connect.collection("products").findOne(myquery, (err, result) => {
    if (err) throw err;
    if (result) {
      db_connect.collection("products").deleteOne(myquery, (err, result) => {
        if (err) throw err;
        res.send(result);
      });
    } else {
      res.status(404).send("Product not found or already deleted");
    }
  });
});

// raportuje sume ilosci i wartosci wszystkich produktow

productRoutes.route("/report").get(function (req, res) {
  let db_connect = dbo.getDb("store");
  db_connect
    .collection("products")
    .aggregate([
      {
        $group: {
          _id: "$name",
          quantity: { $sum: { $toDouble: "$quantity" } },
          value: {
            $sum: {
              $multiply: [{ $toDouble: "$price" }, { $toDouble: "$quantity" }],
            },
          },
        },
      },
    ])
    .toArray((err, result) => {
      if (err) throw err;
      res.send(result);
    });
});

module.exports = productRoutes;
