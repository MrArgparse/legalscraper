from bs4 import BeautifulSoup, Tag, PageElement
from dataclasses import dataclass, asdict
from datetime import datetime
from getuseragent import UserAgent #type: ignore
from rich.logging import RichHandler
from rich import print_json
from typing import Optional
import argparse
import json
import logging
import os
import re
import requests
import sys

@dataclass(kw_only=True)
class MetaObject:
	Title: str
	Date: str
	Runtime: Optional[str] = None
	Studio: Optional[str] = None
	Code: Optional[str] = None
	Poster: Optional[str] = None
	Trailers: Optional[dict[str, str]] = None
	Tags: Optional[list[str]] = None
	FemaleModels: Optional[dict[str | None, dict[str, str | PageElement | None]]] = None
	MaleModels: Optional[dict[str | None, dict[str, str | PageElement | None]]] = None
	TxModels: Optional[dict[str | None, dict[str, str | PageElement | None]]] = None
	UnknownModels: Optional[dict[str | None, dict[str, str | PageElement | None]]] = None

def parse_legalscraper() -> argparse.ArgumentParser:
	parser=argparse.ArgumentParser(prog='legalscraper')
	parser.add_argument('url', nargs='+', help='URL')
	parser.add_argument('--json', '-j', action='store_true', default=False, help='Outputs to a json file')
	parser.add_argument('--output', '-o', default=os.path.join(os.getcwd(), f'AnalVids-Dict-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}.json'), help='Outputs to a json file')

	return parser

def save_json(content: dict[str, MetaObject], path: str, indent: int = 4) -> None:

	with open(path, 'w', encoding='utf8') as json_file:
		json.dump(content, json_file, indent=indent)

def make_request(url: str) -> requests.models.Response:
	headers = {'User-Agent': UserAgent('chrome', limit=1).list[0]}
	r = requests.get(url, headers=headers)

	return r

def get_analvids(html: BeautifulSoup) -> MetaObject:
	code, date, title = None, None, None

	if html.title:
		title = html.title.text.split(' - AnalVids')[0]
		pat = r'\b[A-Za-z]{2,4}\d{2,4}\b'
		match = re.search(pat, title)

		if match:
			code = match.group(0)

	date_pattern = re.compile(r'.*-calendar*')
	date_element = html.find(class_=date_pattern)

	if date_element:
		date = date_element.text.strip()

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

	if not title or not date:
		raise ValueError('Title and Date fields are mandatory.')

	metadata = MetaObject(Title=title, Date=date)

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
	metadata.FemaleModels, metadata.MaleModels, metadata.TxModels, metadata.UnknownModels = get_models(hrefs)

	if code:
		metadata.Code = code

	return metadata

def get_models(hrefs: list[str]) -> tuple[dict[str | None, dict[str, str | PageElement | None]], dict[str | None, dict[str, str | PageElement | None]], dict[str | None, dict[str, str | PageElement | None]], dict[str | None, dict[str, str | PageElement | None]]]:
	female_models = {}
	male_models = {}
	tx_models = {}
	unknown_models = {}

	for h in hrefs:
		r = make_request(h)
		r.raise_for_status
		html = BeautifulSoup(r.content, 'html.parser')
		text_primary = html.find(class_='text-primary')

		if html.title:

			if html.text:
				name = html.title.text.split(' - AnalVids')[0]

		else:
			name = None

		nationality_pattern = re.compile(r'.*/nationality/*')

		if nationality_pattern:
			nationality_ele = html.find('a', href=nationality_pattern)

			if nationality_ele:
				nationality = nationality_ele.next_element

		else:
			nationality = None

		age_element = html.find('td', string='Age:')

		if age_element:
			age_element_nxt_sib = age_element.next_sibling

			if age_element_nxt_sib:
				age = age_element_nxt_sib.text

		else:
			age = None

		img_element =  html.find(class_='model__left model__left--photo')

		if img_element:
			img_tag = img_element.find('img')

			if isinstance(img_tag, Tag):
				resized_src = img_tag.get('src')

				if isinstance(resized_src, str):
					src = resized_src.split('&quot;);')[0]

		else:
			src = None

		if text_primary:
			gender_element = text_primary.find('a')

			if isinstance(gender_element, Tag):
				gender_href = gender_element.get('href')

				if isinstance(gender_href, str):
					gender = gender_href.split('https://www.analvids.com/models/sex/')[-1].split('/nationality/')[0]

					match gender:

						case 'female':
							female_models[name] = {'Age': age, 'Nationality': nationality, 'Image': src}

						case 'male':
							male_models[name] = {'Age': age, 'Nationality': nationality, 'Image': src}

						case 'tx':
							tx_models[name] = {'Age': age, 'Nationality': nationality, 'Image': src}

		else:
			unknown_models[name] = {'Age': age, 'Nationality': nationality, 'Image': src}

	return female_models, male_models, tx_models, unknown_models
		
def main() -> None:
	logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])
	parser = parse_legalscraper()
	args = parser.parse_args(sys.argv[1:])
	metadata_list = {}

	for arg in args.url:

		try:
			r = make_request(arg)
			r.raise_for_status
			html = BeautifulSoup(r.content, 'html.parser')
			metadata = get_analvids(html)
			metadata_list[arg] = metadata

			if args.json:
				save_json(metadata_list, args.output)

			print_json(data=asdict(metadata), indent=4)

		except (KeyError, FileNotFoundError, json.JSONDecodeError, requests.exceptions.ConnectionError, requests.exceptions.HTTPError, ValueError) as e:
			logging.error(f'{type(e).__name__}: {e}')
			sys.exit()

if __name__ == '__main__':
	main()