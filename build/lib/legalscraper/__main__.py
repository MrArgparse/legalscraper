from bs4 import BeautifulSoup, Tag
from dataclasses import asdict, dataclass, field
from datetime import datetime
from getuseragent import UserAgent #type: ignore
from rich.logging import RichHandler
from rich import print_json
from typing import Optional
import argparse
import json
import logging
import os
import random
import re
import requests
import sys
import validators

@dataclass(kw_only=True)
class Info:
	Age: Optional[int] = None
	Nationality: Optional[str] = None
	SRC: Optional[str] = None

@dataclass
class Model:
    Name: Optional[str] = None
    ModelData: Info = field(default_factory=Info)

    def as_dict(self) -> object:
        return {self.Name: self.ModelData.__dict__}

@dataclass(kw_only=True)
class MetaObject:
	Title: Optional[str] = None
	Date: Optional[str] = None
	Runtime: Optional[str] = None
	Studio: Optional[str] = None
	Code: Optional[str] = None
	Poster: Optional[str] = None
	Trailers: Optional[dict[str, str]] = None
	Tags: Optional[list[str]] = None
	FemaleModels: list[object] = field(default_factory=list)
	MaleModels: list[object] = field(default_factory=list)
	TxModels: list[object] = field(default_factory=list)
	UnknownModels: list[object] = field(default_factory=list)

def parse_legalscraper() -> argparse.ArgumentParser:
	parser=argparse.ArgumentParser(prog='legalscraper')
	parser.add_argument('url', nargs='+', help='URL')
	parser.add_argument('--json', '-j', action='store_true', default=False, help='Outputs to a json file')
	parser.add_argument('--output', '-o', default=os.path.join(os.path.expanduser('~'), 'Desktop', f'AnalVids-Dict-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}.json'), help='Specify output path (Defaults to Desktop)')

	return parser

def save_json(content: dict[str, MetaObject], path: str, indent: int = 4) -> None:

	with open(path, 'w', encoding='utf8') as json_file:
		json.dump(content, json_file, indent=indent)

def make_request(url: str) -> requests.models.Response:
	browser_list = ['chrome', 'firefox']
	browser = random.choice(browser_list)
	headers = {'User-Agent': UserAgent(browser, limit=1).list[0]}
	r = requests.get(url, headers=headers)

	return r

def get_analvids(html: BeautifulSoup) -> MetaObject:
	metadata = MetaObject()

	if html.title:
		metadata.Title = html.title.text.split(' - AnalVids')[0]
		pat = r'\b[A-Za-z]{2,4}\d{2,4}\b'
		match = re.search(pat, metadata.Title)

		if match:
			metadata.Code = match.group(0)

	date_pattern = re.compile(r'.*-calendar*')
	date_element = html.find(class_=date_pattern)

	if date_element:
		metadata.Date = date_element.text.strip()

	watch_element = html.find(class_='watch')

	if watch_element:
		video_element = watch_element.find('video')

	trailers = {}

	if isinstance(video_element, Tag):
		poster = video_element.get('data-poster')
		runtime = video_element.get('data-duration')
		trailer_elements = video_element.find_all('source')

		if trailer_elements:

			for ele in trailer_elements:
				size = ele.get('size')
				src = ele.get('src')

				if size and src:
					trailers[size] = src

	if runtime:
		metadata.Runtime = str(runtime)

	if trailers: 
		metadata.Trailers = trailers

	if poster:
		metadata.Poster = str(poster)

	studio_pattern = re.compile(r'^https://www\.analvids\.com/studios/.*$')
	studio_element = html.find('a', href=studio_pattern)

	if studio_element:
		metadata.Studio = studio_element.text

	tags_pattern = re.compile(r'/genre/*')
	tags_element = html.find_all('a', href=tags_pattern)

	if tags_element:
		metadata.Tags = [ele.text for ele in tags_element][1:]

	url_pattern = re.compile(r'^https://www\.analvids\.com/model/.*$')
	matching_hrefs = html.find_all('a', href=url_pattern)
	hrefs = [link.get('href') for link in matching_hrefs]
	hrefs.sort()
	get_models(hrefs, metadata)

	return metadata

def get_models(hrefs: list[str], metadata: MetaObject) -> MetaObject:

	for h in hrefs:
		model = Model()
		r = make_request(h)
		r.raise_for_status
		html = BeautifulSoup(r.content, 'html.parser')
		text_primary = html.find(class_='text-primary')

		if html.title:

			if html.text:
				model.Name = html.title.text.split(' - AnalVids')[0]

		nationality_pattern = re.compile(r'.*/nationality/*')

		if nationality_pattern:
			nationality_ele = html.find('a', href=nationality_pattern)

			if nationality_ele:
				model.ModelData.Nationality = str(nationality_ele.next_element)

		age_element = html.find('td', string='Age:')

		if age_element:
			age_element_nxt_sib = age_element.next_sibling

			if age_element_nxt_sib:
				model.ModelData.Age = int(age_element_nxt_sib.text)

		img_element =  html.find(class_='model__left model__left--photo')

		if img_element:
			img_tag = img_element.find('img')

			if isinstance(img_tag, Tag):
				resized_src = img_tag.get('src')

				if isinstance(resized_src, str):
					model.ModelData.SRC = resized_src.split('&quot;);')[0]

		if text_primary:
			gender_element = text_primary.find('a')

			if isinstance(gender_element, Tag):
				gender_href = gender_element.get('href')

				if isinstance(gender_href, str):
					gender = gender_href.split('https://www.analvids.com/models/sex/')[-1].split('/nationality/')[0]
					dict_model = model.as_dict()

					match gender:

						case 'female':
							metadata.FemaleModels.append(dict_model)

						case 'male':
							metadata.MaleModels.append(dict_model)

						case 'tx':
							metadata.TxModels.append(dict_model)

		else:
			metadata.UnknownModels.append(dict_model)

	return metadata

def query_url(query: str) -> str:
	r = requests.get(f"https://www.analvids.com/api/autocomplete/search?q={query}")
	data = r.json()
	query_link = ''

	if data:
		results = data['terms']

	if len(results) > 0:

		url = results[0].get('url')

		if url:
			query_link = url

	return query_link
		
def main() -> None:
	logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])
	parser = parse_legalscraper()
	args = parser.parse_args(sys.argv[1:])

	for arg in args.url:

		try:

			if validators.url(arg):
				r = make_request(arg)

			else:
				query_link = query_url(arg.replace('_', ' ').replace('.', ' ').replace('-', ' '))

				if query_link:
					r = make_request(query_link)

				else:

					raise ValueError

			r.raise_for_status
			html = BeautifulSoup(r.content, 'html.parser')
			metadata = get_analvids(html)

			if args.json:
				filename = f'AnalVids-Dict-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}.json'

				if os.path.isfile(args.output):
					output = args.output

				elif os.path.isdir(args.output):

					if not os.path.exists(args.output):
						os.makedirs(args.output)

					output = os.path.join(args.output, filename)

				else:
					full_path = os.path.join(os.path.expanduser('~'), filename)
					logging.warning(f'Path does not exist, defaulting to: {full_path}')
					output = os.path.join(os.path.expanduser('~'), 'Desktop', filename)

				save_json(asdict(metadata), output)

			print_json(data=asdict(metadata), indent=4)

		except (KeyError, FileNotFoundError, json.JSONDecodeError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError, ValueError) as e:
			logging.error(f'{type(e).__name__}: {e}')
			sys.exit()

if __name__ == '__main__':
	main()
 
 