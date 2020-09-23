const express = require("express");
const bodyParser = require("body-parser");
const multer = require("multer");
const upload = multer();
const { PythonShell } = require("python-shell");
const { launch, connect } = require("hadouken-js-adapter");
const path = require("path");
const fs = require("fs");

const app = express();

app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());

const port = 3000;

app.use(express.static("public"));

app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname + "/index.html"));
});

app.post("/parse", upload.single("file"), async (req, res) => {
  let uploadFilePath = `./temp/${req.file.originalname}`;
  let parsedFilePath = `./temp/${req.file.originalname.slice(
    0,
    req.file.originalname.length - 4
  )}.json`;

  const uploadPromise = new Promise((resolve, reject) => {
    try {
      fs.writeFile(uploadFilePath, req.file.buffer, resolve);
    } catch (err) {
      reject(err);
    }
  });
  await uploadPromise;

  let options = {
    mode: "text",
    pythonOptions: ["-u"], // get print results in real-time
    parser: console.log,
    scriptPath: "./scripts",
    args: ["--logpath", uploadFilePath, "--outpath", parsedFilePath],
  };

  PythonShell.run("diagnostics_parser.py", options, (err, results) => {
    if (err) throw err;
    // results is an array consisting of messages collected during execution
    console.log("results: %j", results);
    // send data to browser
    res.sendFile(path.join(__dirname + parsedFilePath.slice(1)));
  });

  res.status(200);
});

const manifestUrl = `http://localhost:${port}/app.json`;

app.listen(port, async () => {
  console.log(`Example app listening on port ${port}!`);
  try {
    //Once the server is running we can launch OpenFin and retrieve the port.
    const port = await launch({ manifestUrl });

    //We will use the port to connect from Node to determine when OpenFin exists.
    const fin = await connect({
      uuid: "server-connection", //Supply an addressable Id for the connection
      address: `ws://localhost:${port}`, //Connect to the given port.
      nonPersistent: true, //We want OpenFin to exit as our application exits.
    });

    //Once OpenFin exists we shut down the server.
    fin.once("disconnected", process.exit);
  } catch (err) {
    console.error(err);
  }
});
