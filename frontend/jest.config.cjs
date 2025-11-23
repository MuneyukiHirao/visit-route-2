module.exports = {
  testEnvironment: "jsdom",
  roots: ["<rootDir>"],
  moduleFileExtensions: ["js", "json"],
  moduleNameMapper: {
    "\\.(css)$": "<rootDir>/test/styleMock.js",
  },
  setupFilesAfterEnv: ["<rootDir>/test/setup.js"],
};
