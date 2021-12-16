from flask import Flask, request, jsonify
from flask_restful import Api,Resource
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import pandas as pd
import html5lib
import json
import re


app = Flask(__name__)
CORS(app)
API_NAME = Api(app)
app.config['SECRET_KEY'] = '192b9bdd22ab9ed4d12e236c78afcb9a393ec15f71bbf5dc987d54727823bcbf'
app.config['CORS_HEADERS'] = 'Content-Type'

class BaseUrl(Resource):
    def post(self):
        url = request.get_json()['data']
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        full_name = soup.h1.text
        big_image_url = soup.find_all(class_='pdp-gallery__big-image')[0].get('src')
        small_image_url_lst = []
        for img in soup.find_all(class_='pdp-gallery__small-image'):
            small_image_url_lst.append(img.get('src')),
        product_overview = soup.find_all(class_='pdp-pod-card__item pdp-pod-card__item--vertical pdp-pod-card__item--single pdp-table-sm__item-details')
        spec_tables = soup.find_all(class_='pdp-table__full-specs')
        catalog_num = soup.find_all(class_='pdp-table-sm__catalog-number')
        for i in [0]:
            # getting catalog number and website
            if i == 0:
                catalog_num = catalog_num[0].text
                website = "https://www.thermofisher.com/order/catalog/product/" + catalog_num
            for detail in product_overview[i].find_all(class_="pdp-table-sm__item-detail"):
                if detail.find_all(class_="pdp-table-sm__label bold")[0].text == "Description":
                    description = detail.find_all(class_="pdp-table-sm__value")[0].text
            df = pd.read_html(str(spec_tables))[i]
            df.columns = ['Property', 'Property_value']
            try:
                df.loc[len(df.index)] = ['Description', description] 
            except:
                df.loc[len(df.index)] = ['Description', "No description"]

            df = pd.read_html(str(spec_tables))[i]
            df.columns = ['Property', 'Property_value']
            
            # String cleaning for the df: replace "," with ";" and ":" with "-"
            df = df.replace(',', ';', regex=True).replace(':', '-', regex=True)

            json_str = json.dumps(df.set_index('Property').\
                                  to_dict()['Property_value'], ensure_ascii=False).replace('"', "")

            return_output = jsonify({'full_name': full_name, 
                          'catalog_num': catalog_num,
                          'big_image_url': big_image_url, 
                          'json_str': json_str})
        return return_output

API_NAME.add_resource(BaseUrl, '/api/', methods=['POST', 'GET'])

if __name__ == '__main__':
    app.run()#host='localhost', port=9000, debug=True, threaded=True)
