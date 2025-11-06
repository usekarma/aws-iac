FROM eclipse-temurin:17-jre-jammy

COPY jmx_prometheus_httpserver-1.0.1.jar /jmx_prometheus_httpserver.jar
COPY kconnect-jmx.yml /config/kconnect-jmx.yml

ENTRYPOINT ["java", "-jar", "/jmx_prometheus_httpserver.jar", "9404", "/config/kconnect-jmx.yml"]
