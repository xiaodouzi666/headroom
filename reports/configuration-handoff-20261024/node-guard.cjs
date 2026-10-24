
const fs = require("node:fs");
const path = require("node:path");
const { fileURLToPath } = require("node:url");
const envFile = path.resolve(__dirname, "../../.env");
function deny() { throw new Error("Offline regression forbids network access"); }
function check(file) {
  const name = file instanceof URL ? fileURLToPath(file) : Buffer.isBuffer(file) ? file.toString() : file;
  if (typeof name === "string" && path.resolve(name) === envFile)
    throw new Error("Offline regression forbids project .env reads");
}
for (const key of ["readFile", "readFileSync", "open", "openSync", "createReadStream"]) {
  const original = fs[key];
  fs[key] = function(file, ...args) { check(file); return original.call(this, file, ...args); };
}
for (const key of ["readFile", "open"]) {
  const original = fs.promises[key];
  fs.promises[key] = function(file, ...args) { check(file); return original.call(this, file, ...args); };
}
require("node:net").Socket.prototype.connect = deny;
require("node:tls").connect = deny;
for (const name of ["node:http", "node:https"]) {
  const module = require(name);
  module.request = deny; module.get = deny;
}
const dns = require("node:dns");
for (const key of ["lookup", "resolve", "resolve4", "resolve6", "reverse"]) {
  dns[key] = deny; dns.promises[key] = deny;
}
require("node:module").syncBuiltinESMExports();
