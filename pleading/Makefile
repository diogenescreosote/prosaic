# Shared Makefile for prosaic matter directories.
# Symlink this into each matter directory:
#   ln -sf /path/to/prosaic/pleading/Makefile .
#
# The script path is auto-detected from the symlink target.

PYTHON ?= python3

# Resolve the directory containing the real Makefile (handles spaces in paths).
MAKEFILE_DIR := $(shell perl -e 'use Cwd "abs_path"; my $$p = abs_path("$(lastword $(MAKEFILE_LIST))"); $$p =~ s|/[^/]+$$||; print $$p')
BUILD := $(PYTHON) "$(MAKEFILE_DIR)/build_envelope.py"

SIGN_FLAGS :=
ifdef NAME
SIGN_FLAGS += --sign "$(NAME)"
endif
ifdef DATE
SIGN_FLAGS += --date "$(DATE)"
endif

BUILD_FLAGS :=
ifdef FORCE
BUILD_FLAGS += --force
endif
ifdef VARIANT
BUILD_FLAGS += --variant "$(VARIANT)"
endif

.PHONY: all list clean check-stale both

all:
	$(BUILD) --all $(BUILD_FLAGS) $(SIGN_FLAGS)

# Build every draft envelope in both filing variants (public + sealed).
both:
	$(MAKE) all VARIANT=public
	$(MAKE) all VARIANT=sealed

list:
	$(BUILD) --list $(BUILD_FLAGS)

check-stale:
	$(BUILD) --all --check-stale $(BUILD_FLAGS)

clean:
	rm -rf out

%:
	$(BUILD) $@ $(BUILD_FLAGS) $(SIGN_FLAGS)
