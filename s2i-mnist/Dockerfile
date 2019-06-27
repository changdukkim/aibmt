# s2i-mnist
FROM tensorflow/serving:nightly-devel

# TODO: Put the maintainer name in the image metadata
LABEL maintainer="Changduk Kim <rlackdejr89@gmail.com>"
# Set labels, used by OpenShift, to identify and describe the builder image
LABEL io.k8s.description="mnist s2i builder example" \
      io.k8s.display-name="mnist training s2i builder example" \
      io.openshift.s2i.scripts-url="image:///usr/libexec/s2i" \
      io.openshift.tags="mnist-builder"

COPY ./s2i/bin/ /usr/libexec/s2i
WORKDIR /app

