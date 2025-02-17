from action import Action
class CacheAction(Action):

    def __init__(self, parent=None):
        if parent is None:
            parent = default_parent
        #super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))
    
    def search(self, i):
        i['target_name'] = "cache"
        #logger.debug(f"Searching for cache with input: {i}")
        return self.parent.search(i)

    find = search

    def rm(self, i):
        i['target_name'] = "cache"
        #logger.debug(f"Removing cache with input: {i}")
        return self.parent.rm(i)

    def show(self, run_args):
        self.action_type = "cache"
        res = self.search(run_args)
        logger.info(f"Showing cache with tags: {run_args.get('tags')}")
        cached_meta_keys_to_show = ["uid", "tags", "dependent_cached_path", "associated_script_item"]
        cached_state_keys_to_show = ["new_env", "new_state", "version"]
        for item in res['list']:
            print(f"""Location: {item.path}:
Cache Meta:""")
            for key in cached_meta_keys_to_show:
                if key in item.meta:
                    print(f"""    {key}: {item.meta[key]}""")
            print("""Cached State:""")
            cached_state_meta_file = os.path.join(item.path, "mlc-cached-state.json")
            if not os.path.exists(cached_state_meta_file):
                continue
            try:
                # Load and parse the JSON file containing the cached state
                with open(cached_state_meta_file, 'r') as file:
                    meta = json.load(file)
                    for key in cached_state_keys_to_show:
                        if key in meta:
                            print(f"""    {key}:""", end="")
                            if meta[key] and isinstance(meta[key], dict):
                                print("")
                                utils.printd(meta[key], yaml=False, sort_keys=True, begin_spaces=8)
                            else:
                                print(f""" {meta[key]}""")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
            print("......................................................")
            print("")
            
        return {'return': 0}

    def list(self, args):
        logger.info("Listing all caches.")
        return {'return': 0}