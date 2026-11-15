"""Add real, checked deployment URLs to README after the services are live."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.smoke_api import origin_url,smoke

START='<!-- live-demo:start -->'
END='<!-- live-demo:end -->'


def demo_section(frontend_url,api_url):
    frontend_url,api_url=origin_url(frontend_url),origin_url(api_url)
    return f'''{START}
## Live demo

[Open FireSync]({frontend_url})

- Frontend: Cloudflare Pages, built from `firesync-app/`.
- API: Google Cloud Run, [`phase3/api.py` API documentation]({api_url}/docs).
- Data: loaded NASA FIRMS MODIS and VIIRS detections for British Columbia.
- The harmonized engineering view defaults to an identity baseline. The separate Bayesian mask preview is exploratory; physical accuracy is unvalidated.

The first request after an idle period can take a few seconds while the API starts.
{END}'''


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frontend-url',required=True);p.add_argument('--api-url',required=True)
    a=p.parse_args(argv)
    try:
        frontend,api=origin_url(a.frontend_url),origin_url(a.api_url)
        smoke(api,origin=frontend)
        with urlopen(frontend+'/compare',timeout=30) as res:
            if res.status!=200 or 'text/html' not in res.headers.get('Content-Type',''):
                raise ValueError('The frontend /compare route is not serving the app HTML')
        file=ROOT/'README.md';text=file.read_text();section=demo_section(frontend,api)
        if START in text and END in text:
            before,rest=text.split(START,1);_,after=rest.split(END,1);text=before+section+after
        else:
            title,sep,rest=text.partition('\n');text=title+'\n\n'+section+'\n\n'+rest
        file.write_text(text)
        print('README updated with verified public URLs. Review and commit README.md.')
        return 0
    except Exception as exc:
        print(f'Live-demo update failed: {exc}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
