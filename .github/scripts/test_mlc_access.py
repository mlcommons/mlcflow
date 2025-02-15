import os
import subprocess
import mlc

def process_output(target, action, res):
    if action in ["find"]:
        if "list" not in res:
            raise Exception("'list' entry not found in find result")
            return  # Exit function if there's an error
        if len(res['list']) == 0:
            print(f""" WARNING: No entry found for the particular action and target!""")
        else:
            for item in res['list']:
                print(f"""Item path: {item.path}""")
                if action == "show":
                    print(f"{target} meta:")
                    print(item.meta)

def test_find_repo():
    # This function is seperately written to include the actions which is needed to be tested in a forked repository
    ###### TEST - find repo

    print("###### TEST - find repo")
    # format: <repo_owner>@<repos_name>
    res = mlc.access({
        "automation": "repo",
        "action": "find",
        "repo": "anandhu-eng@mlperf-automations"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find repo) - <repo_owner>@<repos_name>")
        process_output("repo", "find", res)

    # format: <repo_url>
    res = mlc.access({
        "automation": "repo",
        "action": "find",
        "repo": "https://github.com/mlcommons/mlperf-automations.git"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find repo) - <repo_url>")
        process_output("repo", "find", res)

    # format: <repo_uid>
    res = mlc.access({
        "automation": "repo",
        "action": "find",
        "repo": "9cf241afa6074c89"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find repo) - <repo_uid>")
        process_output("repo", "find", res)

    # format: <repo_alias>
    res = mlc.access({
        "automation": "repo",
        "action": "find",
        "repo": "mlcommons@mlperf-automations"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find repo) - <repo_alias>")
        process_output("repo", "find", res)

    # format: <repo_alias>,<repo_uid>
    res = mlc.access({
        "automation": "repo",
        "action": "find",
        "repo": "mlcommons@mlperf-automations,9cf241afa6074c89"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find repo) - <repo_alias>,<repo_uid>")
        process_output("repo", "find", res)

    print("###### TEST find repo SUCCESSFUL.")

def test_list_repo():
    print("###### TEST - list repo")
    res = mlc.access({
        "automation": "repo",
        "action": "list"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST list repo SUCCESSFUL.")

def test_find_cache():
    print("###### TEST - find cache")
    res = mlc.access({
        "automation": "cache",
        "action": "find",
        "tags": "get,imagenet-aux"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find cache)")
        process_output("cache", "find" ,res)
    
    print("###### TEST find cache SUCCESSFUL.")

def test_show_cache():
    print("###### TEST - show cache")
    res = mlc.access({
        "automation": "cache",
        "action": "show",
        "tags": "get,imagenet-aux"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(show cache)")
        process_output("cache", "show" ,res)
    
    print("###### TEST show cache SUCCESSFUL.")

def test_rm_cache():
    print("###### TEST - rm cache")
    res = mlc.access({
        "automation": "cache",
        "action": "rm",
        "tags": "get,imagenet-aux",
        "target": "cache",
        "f": True
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
def test_cp_script():
    print("###### TEST - cp script")
    res = mlc.access({
        "automation": "script",
        "action": "cp",
        "src": "detect-os",
        "dest": "my-os-detect"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST cp script SUCCESSFUL.")

def test_add_repo():
    print("###### TEST - add repo")
    res = mlc.access({
        "automation": "repo",
        "action": "add",
        "repo": "my-new-repo"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print(f"Successfully added repo")

    res = mlc.access({
        "automation": "repo",
        "action": "add",
        "repo": "https://github.com/mlcommons/inference"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print(f"Successfully added repo")
    
    res = mlc.access({
        "automation": "repo",
        "action": "add",
        "repo": "https://mygit.com/myrepo"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print(f"Successfully added repo")
        
    print("###### TEST add repo SUCCESSFUL.")

def test_add_script():
    print("###### TEST - add script")
    res = mlc.access({
        "automation": "script",
        "action": "add",
        "item": "my-script-1",
        "tags": "my,new-tags-1" 
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("script with alias my-script-1 successfully added")

    res = mlc.access({
        "automation": "script",
        "action": "add",
        "item": "my-script-2",
        "tags": "my,new-tags-2" 
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("script with alias my-script-2 successfully added")

    res = mlc.access({
        "automation": "script",
        "action": "add",
        "item": "my-script-3",
        "tags": "my,new-tags-3",
        "template_tags": "detect,cpu" 
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("script with alias my-script-3 successfully added")

    res = mlc.access({
        "automation": "script",
        "action": "add",
        "item": "mlcommons@mlperf-automations:my-script-4",
        "tags": "my,new-tags-4",
        "template_tags": "detect,os"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("script with alias my-script-4 successfully added")

    print("###### TEST add script SUCCESSFUL.")

def test_mv_script():
    res = mlc.access({
        "automation": "script",
        "action": "mv",
        "src": "my-script-1",
        "dest": "moved-my-script-1"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    res = mlc.access({
        "automation": "script",
        "action": "mv",
        "src": "my-script-2",
        "dest": "mlcommons@mlperf-automations:moved-my-script-2"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST mv script SUCCESSFUL.")

def test_show_script():
    print("###### TEST - show script")
    res = mlc.access({
        "automation": "script",
        "action": "show",
        "tags": "run-mlperf,inference"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(show cache)")
        process_output("script", "show" ,res)
    
    res = mlc.access({
        "automation": "script",
        "action": "show",
        "uid": "863735b7db8c44fc"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(show cache)")
        process_output("script", "show" ,res)
    
    res = mlc.access({
        "automation": "script",
        "action": "show",
        "alias": "detect-os,863735b7db8c44fc"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(show cache)")
        process_output("script", "show" ,res)

    res = mlc.access({
        "automation": "script",
        "action": "show",
        "alias": "detect-os"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(show cache)")
        process_output("script", "show" ,res)
    
    print("###### TEST show script SUCCESSFUL.")

def test_find_script():
    print("###### TEST - find script")
    res = mlc.access({
        "automation": "script",
        "action": "find",
        "tags": "run-mlperf,inference"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find script)")
        process_output("script", "find" ,res)
    
    res = mlc.access({
        "automation": "script",
        "action": "find",
        "uid": "863735b7db8c44fc"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find script)")
        process_output("script", "find" ,res)
    
    res = mlc.access({
        "automation": "script",
        "action": "find",
        "alias": "detect-os,863735b7db8c44fc"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find script)")
        process_output("script", "find" ,res)

    res = mlc.access({
        "automation": "script",
        "action": "find",
        "alias": "detect-os"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    else:
        print("Output - TEST(find script)")
        process_output("script", "find" ,res)
    
    print("###### TEST find script SUCCESSFUL.")


def test_rm_script():
    print("###### TEST - rm script")
    res = mlc.access({
        "automation": "script",
        "action": "rm",
        "tags": "app,image,corner-detection",
        "f": True
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    res = mlc.access({
        "automation": "script",
        "action": "rm",
        "item": "get-ipol-src",
        "f": True
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    res = mlc.access({
        "automation": "script",
        "action": "rm",
        "item": "63080407db4d4ac4",
        "f": True
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST rm script SUCCESSFUL.")

def test_list_script():
    print("###### TEST - list script")
    res = mlc.access({
        "automation": "script",
        "action": "list"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST list script SUCCESSFUL.")

def test_list_cache():
    print("###### TEST - list cache")
    res = mlc.access({
        "automation": "cache",
        "action": "list"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST list cache SUCCESSFUL.")

def test_run_script():
    print("###### TEST - run script")
    res = mlc.access({
        "automation": "script",
        "action": "run",
        "tags": "get,imagenet-aux"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    res = mlc.access({
        "automation": "script",
        "action": "run",
        "tags": "get,imagenet-aux,_from.dropbox"
    })
    if res['return'] > 0:
        raise Exception(f"{res['error']}")
    
    print("###### TEST run script SUCCESSFUL.")
    

def run_tests():
    test_list_repo()
    test_find_cache()
    test_run_script()
    test_find_cache()
    test_show_cache()
    test_rm_cache()
    test_cp_script()
    test_add_repo()
    test_add_script()
    test_mv_script()
    test_show_script()
    test_find_script()
    test_rm_script()
    test_list_script()
    test_list_cache()
