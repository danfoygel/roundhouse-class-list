# Agent instructions

After every change, build the page and serve it locally so it can be viewed in a browser:

```
python3 build.py build
python3 -m http.server 8000
```

Report the URL (e.g. `http://localhost:8000/classes.html`) in the session response.
