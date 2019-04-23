## netcdf-replayer

Small little utility designed to load a CF DSG compliant netCDF file and replay it back onto a Kafka topic in either `batch` mode or `stream` mode. Optionally control the timestamps and timedeltas in the original file using configuration parameters.

Data is serialized using the AVRO schema in `schema.avsc`.


## WHY?

This utility is designed to make my life easier. It isn't inteded to be used by many people but has been useful for:

*  Playing back data in a netCDF file with different times and intervals than what is defined in the file.
*  Setting up a quick stream of data for load testing.
*  Transitioning parts of large systems that rely on static files to stream processing.
*  Accepting a standardized data format from collaborators (netCDF/CF/DSG) and being able to stream it into larger systems.


## Data Format

**Simplest example**
```json
{
  "uuid": "1",
  "time": "2019-04-01T00:00:00Z",
  "lat": 30.5,
  "lon": -76.5,
}
```

**Full Example**
```yaml
{
  "uuid": "1",
  "analysis": null,
  "time": "2019-04-01T00:00:00Z",
  "lat": 30.5,
  "lon": -76.5,
  "z": null,
  "values": {
    "salinity": 30.2,
    "temperature":  46.5
  },
  "meta": ""
}
```

*  `values` objects are optional and are a multi-type AVRO `map`.
*  `meta` is optional and open-ended. It is intended to carry along metadata to describe the `values`. I recommend using `nco-json`. This is useful if the system listening to these messages needs some context about the data, like streaming data to a website. YMMV.


## Configuration

This program uses [`Click`](https://click.palletsprojects.com/) for the CLI interface.  I probably spent 50% of the time making this utility just playing around with the CLI interface. I have no idea if what I came up with is mind-blowingly awesome or a bunch of crap. It works. Comments are welcome.

```sh
$ ncreplay
Usage: ncreplay [OPTIONS] FILENAME COMMAND [ARGS]...

Options:
  --brokers TEXT      Kafka broker string (comman separated)  [required]
  --registry TEXT     URL to a Schema Registry  [required]
  --topic TEXT        Kafka topic to send the data to  [required]
  --meta / --no-meta  Include the `nco-json` metadata in each message?
  --help              Show this message and exit.

Commands:
  batch   Batch process a netCDF file in chunks, pausing every [chunk] for...
  stream  Streams each unqiue timestep in the netCDF file every `delta`...
```

### batch

```sh
$ ncreplay /path/to/file.nc batch --help
Usage: ncreplay batch [OPTIONS]

  Batch process a netCDF file in chunks, pausing every [chunk] records
  for [delta] seconds. Optionally change the [starting] time of the file
  and/or change each timedelta using the [factor] and [offset] parameters.

Options:
  -s, --starting [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
  -f, --factor FLOAT
  -o, --offset FLOAT
  -d, --delta FLOAT
  -c, --chunk INTEGER
  --help                          Show this message and exit.
```

### stream

```sh
$ ncreplay /path/to/file.nc stream --help
Usage: ncreplay stream [OPTIONS]

  Streams each unqiue timestep in the netCDF file every [delta] seconds.
  Optionally you can control the [starting] point of the file and this will
  re-calculate all of the timestamps to match the original timedeltas.

Options:
  -s, --starting [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
  -d, --delta FLOAT
  --help                          Show this message and exit
```

## Development / Testing

There are no tests. There is a file at `tests/data/bb_example.nc` that you can play around with. If you need an example kafka ecosystem to play with, the defaults for `ncreplayer` will work out-of-the box with this but you'll have to load the schema into the Schema Registry yourself.

```
$ 
```
