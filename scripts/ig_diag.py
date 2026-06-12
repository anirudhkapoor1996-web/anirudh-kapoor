import os, requests
G="https://graph.facebook.com/v23.0"
T=os.environ["IG_PAGE_TOKEN"]; UID=os.environ["IG_USER_ID"]
def show(label, path, params=None):
    p=dict(params or {}); p["access_token"]=T
    r=requests.get(f"{G}/{path}", params=p, timeout=60)
    print(f"\n=== {label} -> HTTP {r.status_code} ===\n{r.text[:1600]}")
show("debug_token (token type/scopes)", "debug_token", {"input_token": T})
show("/me (who owns this token? should be the PAGE)", "me", {"fields":"id,name"})
show("/me/accounts (page->IG link)", "me/accounts", {"fields":"name,id,instagram_business_account{id,username}"})
show("IG user read", UID, {"fields":"id,username,profile_picture_url,followers_count"})
# decisive: try a media container with a Meta-proven public image (Cloudinary demo)
img="https://res.cloudinary.com/demo/image/upload/w_1080,h_1350,c_fill/sample.jpg"
r=requests.post(f"{G}/{UID}/media", data={"image_url":img,"caption":"diagnostic","access_token":T}, timeout=60)
print(f"\n=== TEST /media with known-good Cloudinary image -> HTTP {r.status_code} ===\n{r.text[:1600]}")
