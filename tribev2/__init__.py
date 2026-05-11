# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from typing import TYPE_CHECKING

__all__ = ["TribeModel"]

if TYPE_CHECKING:
    from tribev2.demo_utils import TribeModel


def __getattr__(name: str):
    if name == "TribeModel":
        from tribev2.demo_utils import TribeModel

        return TribeModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
