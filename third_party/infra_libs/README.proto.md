How to update protos:

1. Have a checkout of chromium.googlesource.com/infra/infra somewhere.
2. `cp -a $infra_checkout/python_pb2/go/chromium/org/luci/* .`
3. `find -name '*_pb2.py' -exec sed -i -f imports.sed '{}' \;`
