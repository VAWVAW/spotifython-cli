{ lib, buildPythonPackage, pythonOlder, fetchPypi, requests, }:

buildPythonPackage rec {
  pname = "spotifython";
  version = "0.2.12";

  disabled = pythonOlder "3.10";

  src = fetchPypi {
    inherit pname version;
    sha256 = "02982e787be23655207a56d1d6218b518d08d48db19dace51c1c2533ce6c597d";
  };

  propagatedBuildInputs = [ requests ];

  doCheck = false;

  format = "setuptools";

  pythonImportsCheck =
    [ "spotifython" "spotifython.playlist" "spotifython.client" ];

  meta = with lib; {
    homepage = "https://github.com/vawvaw/spotifython";
    description =
      "caching python interface to readonly parts of the spotify api";
    license = licenses.gpl3;
  };
}
