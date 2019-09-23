# -*- coding: utf-8 -*-
import base64
import nbformat
import nbconvert
import os
import pynliner
import re
import sys
import time
from bs4 import BeautifulSoup
from shutil import copyfile

def nb2wp(nbfile, out_dir='', template='full', css_file='style.css', 
          save_img=True, img_dir='img', img_url_prefix='img', 
          latex='wp', remove_attrs=True, 
          save_css=False, save_html=False, quiet=False):
    """
    Convert Jupyter notebook file to Wordpress.com HTML.
    
    Parameters:
    nbfile:     The Jupyter notebook file
    out_dir:    Specify output directory. If empty,  a directory  with the same
                name as the notebook file will be created.
    template:   (Optional) nbconvert template file. The default is "full".  You
                may specify standard nbconvert template names such as "full" or
                "basic", or the path of custom nbconvert .TPL file.
    css_file:   Specify CSS file. Default is 'style.css'. If not specified, the
                CSS provided by nbconvert will be used.
    save_img:   Save  inline images  to  external  image files.  Default:  True.
                Setting this  to False  will cause failure in loading the image
                because Wordpress.com disallows "data:" URI.
    img_dir:    The local directory to save images. The path may be relative or
                absolute. If relative, the directory will be under out_dir. 
                Default: "img". 
    img_url_prefix: The  root/parent directory of the images as seen from HTTP.
    latex:      Specify how to convert  Latex directives.  Default is "wp".  If
                empty,  no Latex conversion  will be performed  (the directives
                will be left unchanged).
    remove_attrs: Remove various HTML attributes such as "class", "id" from the
                output HTML file to simplify the file. Default: True 
    save_css:   Save  the CSS  that is used to 'style.css' file in out_dir, for
                debugging. Default: False
    save_html:  Save  the HTML  before it is  processed to 'input.html' file in
                out_dir, for debugging. Default: False
    quiet:      No output to stdout if true. Default: False
    """
    t0 = time.time()
    file = os.path.basename(nbfile)
    filename = os.path.splitext(file)[0]
    if not out_dir:
        out_dir = filename
    if img_url_prefix[-1] == '/':
        img_url_prefix = img_url_prefix[:-1]
     
    def debug(msg):
        if not quiet: print(msg)
       
    with open(nbfile, 'r') as f:
        notebook = nbformat.read(f, as_version=4)

    html_exporter = nbconvert.HTMLExporter()
    if template:
        html_exporter.template_file = template
    debug('Using template: {}'.format(html_exporter.template_file))

    (html, res) = html_exporter.from_notebook_node(notebook)

    #
    # Preprocess CSS and HTML
    #
    if css_file:
        debug('Using CSS file {}'.format(css_file))
        with open(css_file, 'r') as f:
            css = f.read()
    else:
        if res['inlining'] and res['inlining']['css']:
            css = '\n'.join(res['inlining']['css']) + '\n'
        else:
            debug('Warning: no CSS is generated by nbconvert')
            css = ''

    # Replace/remove string patterns in CSS
    patterns = [# comments may contain HTML tag that confuses our regex
                (r'/\*.*?\*/', '', re.I|re.S|re.M), 
                
                # cssutils not able to handle '(' in CSS selector
                (r'[_0-9a-zA-Z-#.:*]+\(.*?}', '', re.I|re.S|re.M), 
                
                # cssutils not able to handle ~ in CSS selector
                (r'[_0-9a-zA-Z-#.:*]+\s*~', '', re.I|re.S|re.M), 
               ]
    for str_pat, repl, flag in patterns:
        pat = re.compile(str_pat, flag)
        css = pat.sub(repl, css)
    
    if save_css:
        with open(os.path.join(out_dir, 'style.css'), 'w') as f:
            f.write(css)

    patterns = [# silly character after headings
                (r'&#182;', '', re.I|re.S|re.M), 
                
                # link to local file custom.css, which pynliner couldn't handle
                (r'<link rel="stylesheet" .*?>', '', re.I|re.S|re.M),
                
                # remove the whole <head> as it contains duplicate CSS with full template
                (r'<head.*</head>', '', re.I|re.S|re.M) 
                ]
    for str_pat, repl, flag in patterns:
        pat = re.compile(str_pat, flag)
        html = pat.sub(repl, html)
    
    if save_html:
        with open(os.path.join(out_dir, 'input.html'), 'w') as f:
            f.write(html)

    #
    # CSS inlining
    #
    inliner = pynliner.Pynliner()
    if css:
        #print('CSS is found')
        inliner = inliner.from_string(html).with_cssString(css)
    else:
        inliner = inliner.from_string(html)

    html = inliner.run()
    
    #
    # Process images
    #
    if save_img:
        soup = BeautifulSoup(html, 'html.parser')
        images = soup.find_all('img')
        img_parent_path = os.path.join(out_dir, img_dir)
        if images and not os.path.exists(img_parent_path):
            os.makedirs(img_parent_path)
                
        for img_i, img in enumerate(images):
            src = img['src']
            if 'data:' in src.lower():
                # data: URI
                img_type = re.search(r'data:image/([a-z0-9]+)', src, re.I).group(1)
                img_encoding = re.search(r'data:image/[a-z]+;([a-z0-9]+)', src, re.I).group(1)
                data = re.search(r'data:image/[a-z0-9]+;[a-z0-9]+,(.*)', src, re.I).group(1)
                
                img_file = 'img{}.{}'.format(img_i, img_type)
                img_path = os.path.join(img_parent_path, img_file)
                
                with open(img_path, 'wb') as f:
                    if img_encoding == 'base64':
                        f.write(base64.b64decode(data))
                    else:
                        raise RuntimeError('Unsupporte image encoding "{}"'.format(img_encoding))
                    
                img['src'] = img_url_prefix + '/' + img_file
            elif 'http:' not in src.lower() and 'https:' not in src.lower():
                # Local file
                img_filename = os.path.basename(src)
                img_ext = os.path.splitext(img_filename)[1]
                img_file = 'img{}{}'.format(img_i, img_ext)
                img_path = os.path.join(img_parent_path, img_file)
                copyfile(src, img_path)
                img['src'] = img_url_prefix + '/' + img_file

        html = str(soup)

    #
    # clean up the HTML
    #
    patterns = [# Remove inline <style> still in the HTML (in the body)
                (r'<style.*?</style>', '', re.I|re.S|re.M),
                ]
    
    for str_pat, repl, flag in patterns:
        pat = re.compile(str_pat, flag)
        html = pat.sub(repl, html)
    
    #
    # Remove classes and ids
    #
    if remove_attrs:
        soup = BeautifulSoup(html, 'html.parser')
        elements = soup.find_all()
        for el in elements:
            del el['class']
            del el['id']
        html = str(soup)

    
    #
    # Process latex last (otherwise '&' will be escaped)
    #
    if latex == "wp":
        # Stage 1: replace "$ formula $" into "@beginlatex@ formula @endlatex1@",
        #             and  "$$ formula $$" into "@beginlatex@ formula @endlatex2@"
        pat = re.compile(r'(\${1,2})((?:\\.|[\s\S])*?)\1')
        while True:
            m = pat.search(html)
            if m is None:
                break
            
            formula = m.group(2)
            html = html[:m.start()] + '@beginlatex@' + formula + \
                  ('@endlatex2@' if m.group(1)=='$$' else '@endlatex1@') + \
                  html[m.end():]
            
        # Stage 2: replace '@beginlatex@' and '@endlatex@@'
        html = html.replace('@beginlatex@', '$latex ') \
                   .replace('@endlatex1@', ' &bg=ffffff&s=2 $') \
                   .replace('@endlatex2@', ' &bg=ffffff&s=4 $')
    elif not latex:
        pass
    else:
        raise RuntimeError("Invalid latex argument value '{}'".format(latex))

    
    #
    # Save HTML
    #
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    
    htmlfile = os.path.join(out_dir, filename + '.html')
    with open(htmlfile, 'w') as f:
        f.write(html)
        
    elapsed = time.time() - t0
    debug('{}: {} bytes written in {:.3f}s'.format(htmlfile, len(html), elapsed))


if __name__ == '__main__':
    nb2wp('Readme.ipynb', out_dir='out/tmp', 
          img_url_prefix='https://raw.githubusercontent.com/bennylp/nb2wp/master/out/demo2/img')
    