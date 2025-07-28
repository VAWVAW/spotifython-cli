{ lib, python3, installShellFiles, spotifython, }:

python3.pkgs.buildPythonApplication rec {
  pname = "spotifython-cli";
  version = "0.3.7";

  src = ./.;

  nativeBuildInputs = [ installShellFiles ];
  propagatedBuildInputs = [ spotifython python3.pkgs.click ];

  postInstall = ''
    _SPOTIFYTHON_CLI_COMPLETE=bash_source $out/bin/spotifython-cli > completion.bash
    _SPOTIFYTHON_CLI_COMPLETE=zsh_source $out/bin/spotifython-cli > completion.zsh
    _SPOTIFYTHON_CLI_COMPLETE=fish_source $out/bin/spotifython-cli > completion.fish
    installShellCompletion --cmd ${pname} completion.{bash,zsh,fish}
  '';

  doCheck = false;

  format = "setuptools";

  meta = with lib; {
    homepage = "https://github.com/vawvaw/spotifython-cli";
    description =
      "command line interface for spotifython intended for use with spotifyd";
    license = licenses.gpl3;
    mainProgram = "spotifython-cli";
  };
}
