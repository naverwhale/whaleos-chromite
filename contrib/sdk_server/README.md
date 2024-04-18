# Cros SDK Server

## About

The SDK Server provides a user interface for many Build API, cros, and repo commands with the overall goal of managing a single chroot, intended to make the average ChromeOS developer workflow simpler.

## Running the SDK Server

To run the SDK server simply run the sdk_server symlink found in chromite/contrib/sdk_server. This will start both the grpc server and the web server. To close the server simply kill the process using CTRL+C. In the future we’ll add functionality for the server to be run as a cros command.

## Features

- Chroot Information, including
    - Date chroot was created
    - Date last updated
    - Path to Chroot
    - Chroot Version

- Menus for calling a few Build API endpoints which support the options defined in their request protos. These endpoints include:
    - SdkService/Update
    - SdkService/Create
    - SdkService/Delete
    - ImageService/Create

- A “Build Packages” menu, which works by running the three Build API endpoints:
    - SysrootService/Create - through build packages
    - SysrootService/InstallToolchain - through build packages
    - SysrootService/InstallPackages - through build packages

- Endpoints that are listed by the MethodService/Get endpoint are callable by writing custom protos in JSON format (via the “Custom” menu)
- All above features produce logs that can be toggled and viewed on the dashboard. A history is stored which can be cleared.

- Support for cros_workon commands, including
    - Listing all working packages per board
    - Options to build individual packages
    - A button to stop workon on any package
    - Info modals (which display the results of cros workon info) per package
    - An “Add Packages” menu to begin working on any package

- Repo interactions, including
    - A panel displaying the output from repo status (relevant files and their
    - statuses in the staging area, working directory, etc.)
    - A repo sync button

## Future Work

- An integrated bug reporting tool, allowing users to easily upload bugs with stored log information via a Buganizer API
- Ensure that running commands are logged if the server is interrupted
- Modify to use gRPC web, rather than route everything through Python/Flask
- Implementing dedicated cros flash/deploy endpoints
- Expand functionality to handle multiple chroots/branching, in alignment with the goals of go/cros-sdk-server
