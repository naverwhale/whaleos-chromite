# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

IMPORT_PATTERN = "chromite.api.controller.%s"

# Endpoint ran successfully.
RETURN_CODE_SUCCESS = 0
# Unrecoverable error. This includes things from missing required inputs to
# unhandled exceptions.
RETURN_CODE_UNRECOVERABLE = 1
# The endpoint did not complete successfully, but did complete via a well
# handled path and produced actionable information relevant to the failure in
# the response.
RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE = 2
# Notes the endpoint completed via a well handled path, but the result was not
# a successful execution of the endpoint.
RETURN_CODE_COMPLETED_UNSUCCESSFULLY = 3


# Validate only request successfully validated.
RETURN_CODE_VALID_INPUT = 0
# Validate only request did not pass validation.
RETURN_CODE_INVALID_INPUT = 1
