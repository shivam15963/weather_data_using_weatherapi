import logging
import xml.etree.ElementTree as ET
from pydantic import BaseModel, validator
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from requests import Session, HTTPError
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


API_KEY = "7679b027b85c46c7b40133852230703"
logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.DEBUG)

# These error codes can be retried according to WeatherAPI documentation. Ref: https://www.weatherapi.com/docs/#intro-request
retry_strategy = Retry(total=5, status_forcelist=[
    500, 503, 504], backoff_factor=2)
adapter = HTTPAdapter(max_retries=retry_strategy)
session_object = Session()
session_object.mount("https://", adapter)
session_object.mount("http://", adapter)

app = FastAPI(title="Verloop Assignment - 1", version="1.0.0", contact={
    "name": "Shivam Mehla"
}, docs_url="/")


class cityParameters(BaseModel):
    """Class to validate request parameters for /getCurrentWeather

    Args:
        BaseModel: Base class for validators

    Raises:
        HTTPException: Raised when empty city is given
        HTTPException: Raised when invalid output format is given
    """
    city: str
    output_format: str

    @validator("city")
    def check_if_string_is_empty(cls, city):
        if not city:
            raise HTTPException(
                status_code=400, detail="The city string is empty")
        return city

    @validator("output_format")
    def check_if_output_format_is_valid(cls, output_format):
        output_format = output_format.lower()
        allowed_output_format = {"json", "xml"}
        if output_format not in allowed_output_format:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid output format: '{output_format}'. Only allowed formats are {allowed_output_format}")
        return output_format


def construct_response(city: str, output_format: str, response: Response) -> Response:
    """Constructs response in the given format

    Args:
        city (str): city given to us by the user
        output_format (str): Format in which to send the output. Only "xml", "json" allowed.
        response (Response): Response object gotten from google maps API

    Returns:
        Response: A response object to be sent to the user with the requested response format
    """
    if output_format == "json":
        json_response = response.json()
        json_status_code = response.status_code
        json_output = {"Weather": "",
                       "Latitude": "",
                       "Longitude": "",
                       "City": city}
        if json_status_code == 200:
            try:
                # [0] is ok because we are sending only one city at a time
                json_output["Weather"] = str(json_response["current"]["temp_c"]) + " C"
                json_output["Latitude"] = json_response["location"]["lat"]
                json_output["Longitude"] = json_response["location"]["lon"]
                json_output["City"] = str(json_response["location"]["name"]) + " " + str(json_response["location"]["country"])
            except KeyError as err:
                logging.error(err)
        return JSONResponse(status_code=200, content=json_output, media_type="application/json")
    else:
        xml_response = ET.fromstring(response.text)

        xml_output = ET.Element("root")
        temperature_element = ET.SubElement(xml_output, "Temperature")
        city_element = ET.SubElement(xml_output, "City")
        lat_element = ET.SubElement(xml_output, "Latitude")
        lng_element = ET.SubElement(xml_output, "Longitude")
        temperature_element.text = ""
        lat_element.text = ""
        lng_element.text = ""
        if xml_response.find("location").find("name").text.lower() == city.lower():
            try:
                city_element.text = str(xml_response.find("location").find(
                    "name").text)
                temperature_element.text = str(xml_response.find("current").find(
                    "temp_c").text) + " C"
                lng_element.text = str(xml_response.find("location").find(
                    "lon").text)
                lat_element.text = str(xml_response.find("location").find(
                    "lat").text)
            except AttributeError as err:
                logging.error(err)
        return Response(content=ET.tostring(xml_output, encoding="UTF-8"), status_code=200,
                        media_type="application/xml")


def get_data_from_weather_api(city: str, output_format: str) -> Response:
    """Gets data from Weather API and handles errors

    Args:
        city (str): The city for which weather needs to be found
        output_format (str): Format in which to send the output. Only "xml", "json" allowed.

    Raises:
        HTTPException: Raised when call to API servers fail after multiple retries

    Returns:
        Response : A response object to be sent to the user with the requested response format
    """
    url = f"https://api.weatherapi.com/v1/current.{output_format}"
    parameters = {"q": city, "key": API_KEY}
    response = session_object.get(url=url, params=parameters)
    try:
        response.raise_for_status()
    except HTTPError:
        logging.error(f"Received error {response.status_code}:{response.text}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    else:
        logging.debug("Response received: {resp.text}")
        return construct_response(city=city, output_format=output_format, response=response)


@app.post("/getCurrentWeather")
def get_weather_data_for_city(params: cityParameters) -> Response:
    """Function that gets city as input and gives the weather, latitutde and longitude in the requested format

    Args:
        params (cityParameters): Request Parameters

    Returns:
        Response : A response object to be sent to the user with the requested response format
    """
    params = params.dict()
    return get_data_from_weather_api(city=params["city"], output_format=params["output_format"])
