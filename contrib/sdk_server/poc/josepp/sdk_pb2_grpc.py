# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

from chromite.api.gen.chromite.api import (
    sdk_pb2 as chromite_dot_api_dot_sdk__pb2,
)


class SdkServiceStub(object):
    """SDK operations."""

    def __init__(self, channel):
        """Constructor.

        Args:
          channel: A grpc.Channel.
        """
        self.Create = channel.unary_unary(
            "/chromite.api.SdkService/Create",
            request_serializer=chromite_dot_api_dot_sdk__pb2.CreateRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.CreateResponse.FromString,
        )
        self.Delete = channel.unary_unary(
            "/chromite.api.SdkService/Delete",
            request_serializer=chromite_dot_api_dot_sdk__pb2.DeleteRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.DeleteResponse.FromString,
        )
        self.Clean = channel.unary_unary(
            "/chromite.api.SdkService/Clean",
            request_serializer=chromite_dot_api_dot_sdk__pb2.CleanRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.CleanResponse.FromString,
        )
        self.Unmount = channel.unary_unary(
            "/chromite.api.SdkService/Unmount",
            request_serializer=chromite_dot_api_dot_sdk__pb2.UnmountRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.UnmountResponse.FromString,
        )
        self.Update = channel.unary_unary(
            "/chromite.api.SdkService/Update",
            request_serializer=chromite_dot_api_dot_sdk__pb2.UpdateRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.UpdateResponse.FromString,
        )
        self.Uprev = channel.unary_unary(
            "/chromite.api.SdkService/Uprev",
            request_serializer=chromite_dot_api_dot_sdk__pb2.UprevRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.UprevResponse.FromString,
        )
        self.CreateSnapshot = channel.unary_unary(
            "/chromite.api.SdkService/CreateSnapshot",
            request_serializer=chromite_dot_api_dot_sdk__pb2.CreateSnapshotRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.CreateSnapshotResponse.FromString,
        )
        self.RestoreSnapshot = channel.unary_unary(
            "/chromite.api.SdkService/RestoreSnapshot",
            request_serializer=chromite_dot_api_dot_sdk__pb2.RestoreSnapshotRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.RestoreSnapshotResponse.FromString,
        )
        self.UnmountPath = channel.unary_unary(
            "/chromite.api.SdkService/UnmountPath",
            request_serializer=chromite_dot_api_dot_sdk__pb2.UnmountPathRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.UnmountPathResponse.FromString,
        )
        self.BuildPrebuilts = channel.unary_unary(
            "/chromite.api.SdkService/BuildPrebuilts",
            request_serializer=chromite_dot_api_dot_sdk__pb2.BuildPrebuiltsRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.BuildPrebuiltsResponse.FromString,
        )
        self.BuildSdkTarball = channel.unary_unary(
            "/chromite.api.SdkService/BuildSdkTarball",
            request_serializer=chromite_dot_api_dot_sdk__pb2.BuildSdkTarballRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.BuildSdkTarballResponse.FromString,
        )
        self.CreateManifestFromSdk = channel.unary_unary(
            "/chromite.api.SdkService/CreateManifestFromSdk",
            request_serializer=chromite_dot_api_dot_sdk__pb2.CreateManifestFromSdkRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.CreateManifestFromSdkResponse.FromString,
        )
        self.CreateBinhostCLs = channel.unary_unary(
            "/chromite.api.SdkService/CreateBinhostCLs",
            request_serializer=chromite_dot_api_dot_sdk__pb2.CreateBinhostCLsRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.CreateBinhostCLsResponse.FromString,
        )
        self.UploadPrebuiltPackages = channel.unary_unary(
            "/chromite.api.SdkService/UploadPrebuiltPackages",
            request_serializer=chromite_dot_api_dot_sdk__pb2.UploadPrebuiltPackagesRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.UploadPrebuiltPackagesResponse.FromString,
        )
        self.BuildSdkToolchain = channel.unary_unary(
            "/chromite.api.SdkService/BuildSdkToolchain",
            request_serializer=chromite_dot_api_dot_sdk__pb2.BuildSdkToolchainRequest.SerializeToString,
            response_deserializer=chromite_dot_api_dot_sdk__pb2.BuildSdkToolchainResponse.FromString,
        )


class SdkServiceServicer(object):
    """SDK operations."""

    def Create(self, request, context):
        """Create method, supports replacing an existing chroot."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def Delete(self, request, context):
        """Delete a chroot. Added in R79."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def Clean(self, request, context):
        """Clean up unneeded files from the chroot. Added in R81."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def Unmount(self, request, context):
        """Unmount a chroot. Added in R81.
        Deprecated.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def Update(self, request, context):
        """Update the chroot."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def Uprev(self, request, context):
        """Uprev the SDK.
        Creates code changes to uprev the SDK version file and prebuilt conf files.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def CreateSnapshot(self, request, context):
        """Create a chroot snapshot. Added in R83."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RestoreSnapshot(self, request, context):
        """Restore a chroot to a snapshot. Added in R83."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def UnmountPath(self, request, context):
        """Unmount a filesystem path and any submounts under it.  Added in R86."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def BuildPrebuilts(self, request, context):
        """Builds the binary packages that comprise the SDK."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def BuildSdkTarball(self, request, context):
        """Creates a tarball from a previously built SDK."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def CreateManifestFromSdk(self, request, context):
        """Create a manifest file showing the ebuilds in an SDK."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def CreateBinhostCLs(self, request, context):
        """Creates CLs to point the binhost at uploaded prebuilts."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def UploadPrebuiltPackages(self, request, context):
        """Uploads prebuilt packages (such as built by BuildPrebuilts)."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def BuildSdkToolchain(self, request, context):
        """Build toolchain cross-compilers for the SDK."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_SdkServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "Create": grpc.unary_unary_rpc_method_handler(
            servicer.Create,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.CreateRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.CreateResponse.SerializeToString,
        ),
        "Delete": grpc.unary_unary_rpc_method_handler(
            servicer.Delete,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.DeleteRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.DeleteResponse.SerializeToString,
        ),
        "Clean": grpc.unary_unary_rpc_method_handler(
            servicer.Clean,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.CleanRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.CleanResponse.SerializeToString,
        ),
        "Unmount": grpc.unary_unary_rpc_method_handler(
            servicer.Unmount,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.UnmountRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.UnmountResponse.SerializeToString,
        ),
        "Update": grpc.unary_unary_rpc_method_handler(
            servicer.Update,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.UpdateRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.UpdateResponse.SerializeToString,
        ),
        "Uprev": grpc.unary_unary_rpc_method_handler(
            servicer.Uprev,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.UprevRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.UprevResponse.SerializeToString,
        ),
        "CreateSnapshot": grpc.unary_unary_rpc_method_handler(
            servicer.CreateSnapshot,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.CreateSnapshotRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.CreateSnapshotResponse.SerializeToString,
        ),
        "RestoreSnapshot": grpc.unary_unary_rpc_method_handler(
            servicer.RestoreSnapshot,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.RestoreSnapshotRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.RestoreSnapshotResponse.SerializeToString,
        ),
        "UnmountPath": grpc.unary_unary_rpc_method_handler(
            servicer.UnmountPath,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.UnmountPathRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.UnmountPathResponse.SerializeToString,
        ),
        "BuildPrebuilts": grpc.unary_unary_rpc_method_handler(
            servicer.BuildPrebuilts,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.BuildPrebuiltsRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.BuildPrebuiltsResponse.SerializeToString,
        ),
        "BuildSdkTarball": grpc.unary_unary_rpc_method_handler(
            servicer.BuildSdkTarball,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.BuildSdkTarballRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.BuildSdkTarballResponse.SerializeToString,
        ),
        "CreateManifestFromSdk": grpc.unary_unary_rpc_method_handler(
            servicer.CreateManifestFromSdk,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.CreateManifestFromSdkRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.CreateManifestFromSdkResponse.SerializeToString,
        ),
        "CreateBinhostCLs": grpc.unary_unary_rpc_method_handler(
            servicer.CreateBinhostCLs,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.CreateBinhostCLsRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.CreateBinhostCLsResponse.SerializeToString,
        ),
        "UploadPrebuiltPackages": grpc.unary_unary_rpc_method_handler(
            servicer.UploadPrebuiltPackages,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.UploadPrebuiltPackagesRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.UploadPrebuiltPackagesResponse.SerializeToString,
        ),
        "BuildSdkToolchain": grpc.unary_unary_rpc_method_handler(
            servicer.BuildSdkToolchain,
            request_deserializer=chromite_dot_api_dot_sdk__pb2.BuildSdkToolchainRequest.FromString,
            response_serializer=chromite_dot_api_dot_sdk__pb2.BuildSdkToolchainResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "chromite.api.SdkService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
