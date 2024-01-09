"""Ray PandasTextDatasink Module."""

import io
import logging
from typing import Any, Dict, Optional

from pyarrow import csv
from ray.data.block import BlockAccessor
from ray.data.datasource.block_path_provider import BlockWritePathProvider

from awswrangler.distributed.ray.datasources.file_datasink import _BlockFileDatasink

_logger: logging.Logger = logging.getLogger(__name__)


class ArrowCSVDatasink(_BlockFileDatasink):
    """A datasink that writes CSV files using Arrow."""

    def __init__(
        self,
        path: str,
        *,
        block_path_provider: Optional[BlockWritePathProvider] = None,
        dataset_uuid: Optional[str] = None,
        open_s3_object_args: Optional[Dict[str, Any]] = None,
        pandas_kwargs: Optional[Dict[str, Any]] = None,
        write_options: Optional[Dict[str, Any]] = None,
        **write_args: Any,
    ):
        super().__init__(
            path,
            file_format="csv",
            block_path_provider=block_path_provider,
            dataset_uuid=dataset_uuid,
            open_s3_object_args=open_s3_object_args,
            pandas_kwargs=pandas_kwargs,
            **write_args,
        )

        self.write_options = write_options or {}

    def write_block(self, file: io.TextIOWrapper, block: BlockAccessor) -> None:
        """
        Write a block of data to a file.

        Parameters
        ----------
        block : BlockAccessor
        file : io.TextIOWrapper
        """
        csv.write_csv(block.to_arrow(), file, csv.WriteOptions(**self.write_options))