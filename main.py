from flask import Flask, request, jsonify
from flask_restful import Api,Resource
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import pandas as pd
import recordlinkage
from fuzzywuzzy.fuzz import WRatio
from recordlinkage.base import BaseCompareFeature
import html5lib
import re
import json


app = Flask(__name__)
CORS(app)
API_NAME = Api(app)
app.config['SECRET_KEY'] = '192b9bdd22ab9ed4d12e236c78afcb9a393ec15f71bbf5dc987d54727823bcbf'
app.config['CORS_HEADERS'] = 'Content-Type'

#### Custom function for deduplication ####
class CompareFuzzWRatio(BaseCompareFeature):

    def _compute_vectorized(self, s1, s2):
        """
        fuzzywuzzy.fuzz.WRatio for 2 vectors (strip non-alphanumeric before compare)
        """
        def custom_wratio(x, y):
            # Strip non-alphanumeric before comparisons
            x = "".join(re.findall("[a-zA-Z0-9]+", x))
            y = "".join(re.findall("[a-zA-Z0-9]+", y))
            return WRatio(x,y)
        
        sim = pd.concat([s1, s2], axis=1).apply(lambda x: custom_wratio(x[0], x[1])/100, axis=1)

        return sim
    
#### App Routing ####

class FuzzyMatch(Resource):
    def post(self):
        """
        Take a JSON with 3 fields: 'search_phrase', 'threshold', and 'JSON_str' which is the dataframe
        and output a JSON string with top fuzzy matches
        """
        
        JSON_body = request.get_json()['data']
        search_phrase = JSON_body['search_phrase']
        JSON_str = JSON_body['JSON_str']
        threshold = JSON_body['threshold']

        df = pd.DataFrame(eval(JSON_str.replace('null', """ " " """))).set_index('crca9_uniqueid')

        def preprocessing(txt):
            return "".join(re.findall("[a-zA-Z0-9]+", txt)).lower()
        score = 1/100 * (0.6*df['crca9_cslname'].apply(lambda x: WRatio(preprocessing(x), preprocessing(search_phrase))) + \
                         0.4*df['crca9_standardequipmenttype']\
                         .apply(lambda x: WRatio(preprocessing(x), preprocessing(search_phrase)))).sort_values(ascending=False)
        if score[score >= threshold].shape[0] >= 5:
            df = df.loc[score[score >= threshold].index,:].reset_index()
        else:
            df = df.loc[score.index,:].head().reset_index()

        return_output = jsonify({'fuzzymatched': df.to_dict('records')})
        return return_output

class DeDup(Resource):
    def post(self):
        """
        Take a JSON string with 3 fields: 'crca9_eimstandardequipmenttypeid', 'crca9_equipmentmake', 'crca9_equipmentmodel' 
        and output a JSON string with potential duplicated scores
        """
        
        StdEq_JSON = request.get_json()['data']

        df = pd.DataFrame(eval(StdEq_JSON)).set_index('crca9_eimstandardequipmenttypeid')

        Full_Index_Table = recordlinkage.index.Full().index(df)

        compare = recordlinkage.Compare()
        #compare.string('crca9_equipmentmodel','crca9_equipmentmodel', method='levenshtein', label = 'score')
        compare.add(CompareFuzzWRatio('crca9_equipmentmodel','crca9_equipmentmodel', label='score'))
        #compare.string('crca9_equipmentmake','crca9_equipmentmake', method='levenshtein', label = 'crca9_equipmentmake')
        comparison_vectors = compare.compute(Full_Index_Table, df)
        comparison_vectors = comparison_vectors[comparison_vectors.sum(axis=1)>0.6]

        output = []

        for (idx1, idx2), scoredict in comparison_vectors.to_dict('index').items():
            toappend = {
                'idx1': idx1,
                'item1': df.loc[idx1,'crca9_equipmentmodel'],
                'idx2': idx2,
                'item2': df.loc[idx2,'crca9_equipmentmodel'],
                'score': str(scoredict['score'])
            }
            output.append(toappend)

        return_output = jsonify({'deduped': output})
        return return_output
        

class ScrapeThermo(Resource):
    def post(self):
        """
        Take a JSON string with 1 field: 'data' that contains the URL of the thermofisher website to scrape
        and output a JSON string with 4 fields: 'full_name', 'catalog_num', 'big_image_url', and the scraped 'json_str'
        """
        url = request.get_json()['data']
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        #print(soup)
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

API_NAME.add_resource(ScrapeThermo, '/scrapethermo', methods=['POST', 'GET'])
API_NAME.add_resource(FuzzyMatch, '/fuzzymatch', methods=['POST', 'GET'])
API_NAME.add_resource(DeDup, '/dedup', methods=['POST', 'GET'])

if __name__ == '__main__':
    app.run(host='localhost', port=9000, debug=True, threaded=True)
