import org.yaml.snakeyaml.Yaml

class YamlLoader {

    static Map load(String filePath) {

        def file = new File(filePath)
        if (!file.exists()) {
            throw new FileNotFoundException("YAML file not found: " + filePath)
        }

        def yaml = new Yaml()
        return yaml.load(file.text)
    }
}