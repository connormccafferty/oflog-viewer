const express = require("express");
var bodyParser = require("body-parser");
var multer = require("multer");
var upload = multer();
const { spawn } = require("child_process");
var path = require("path");
const fs = require("fs");

const app = express();

app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());

app.use(express.static("public"));

const port = 3000;

app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname + "/index.html"));
});

app.post("/parse", upload.single("file"), async (req, res) => {
  // console.log(req.file);
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

  // spawn new child process to call the python script
  const python = spawn("python", [
    "diagnostics_parser.py",
    "--logpath",
    uploadFilePath,
    "--outpath",
    parsedFilePath,
  ]);
  // // collect data from script
  python.stdout.on("data", function (data) {
    console.log("python script success");
  });
  // // in close event we are sure that stream from child process is closed
  python.on("close", (code) => {
    console.log(`child process close all stdio with code ${code}`);
    // send data to browser
    res.sendFile(path.join(__dirname + parsedFilePath.slice(1)));
  });
  res.status(200);
});

app.listen(port, () =>
  console.log(`Example app listening on port 
 ${port}!`)
);
